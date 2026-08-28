"""Run-bound MLflow logging.

The fluent API (``mlflow.set_tag``, ``mlflow.end_run``) writes to whichever
run sits on ``mlflow.tracking.fluent._active_run_stack``, and that stack is
a thread-local. Every ``/plugin/mcp/execute`` request is an asyncio task on
the single aiohttp event-loop thread, so concurrent runs share one pointer:
a bare ``end_run()`` terminates whichever run is on top, which during
overlap belongs to another request, and a ``set_tag()`` with an empty stack
silently mints a phantom run in the active experiment.

``RunTracker`` binds an ``MlflowClient`` to one run id so every write names
the run it belongs to and no process-wide state is involved.
"""

import logging

from mlflow.tracking import MlflowClient

log = logging.getLogger("plugins.mcp")

# mlflow rejects an oversized value outright. Truncating keeps a completed
# run from being recorded as failed just because its reasoning was long.
_MAX_TAG_CHARS = 5000
_MAX_PARAM_CHARS = 6000


def resolve_experiment_id(name: str, client: MlflowClient = None) -> str:
    """Experiment id for ``name``, creating the experiment if absent.

    Deliberately not ``mlflow.set_experiment``: that mutates the
    process-wide active experiment this module exists to stay clear of.
    """
    client = client or MlflowClient()
    experiment = client.get_experiment_by_name(name)
    if experiment is not None:
        return experiment.experiment_id
    try:
        return client.create_experiment(name)
    except Exception:
        # Lost the race with a concurrent creator; re-read rather than fail.
        experiment = client.get_experiment_by_name(name)
        return experiment.experiment_id if experiment else "0"


class RunTracker:
    """MLflow writes bound to a single run id."""

    def __init__(self, run_id: str, client: MlflowClient = None):
        self.run_id = run_id
        self._client = client or MlflowClient()
        self._terminated = False

    @classmethod
    def start(cls, experiment_name: str, run_name: str,
              client: MlflowClient = None) -> "RunTracker":
        """Mint a run in ``experiment_name`` without activating it."""
        client = client or MlflowClient()
        run = client.create_run(
            experiment_id=resolve_experiment_id(experiment_name, client),
            tags={"mlflow.runName": run_name},
        )
        return cls(run.info.run_id, client)

    @classmethod
    def bind(cls, run_id: str, experiment_name: str, run_name: str,
             client: MlflowClient = None) -> "RunTracker":
        """Track ``run_id``, or mint a run when the caller has none.

        Workflows are normally handed a run id by the orchestrator, which
        owns terminating it. Invoked directly (tests, scripts) they mint
        and terminate their own.
        """
        if run_id:
            return cls(run_id, client)
        return cls.start(experiment_name, run_name, client)

    @property
    def terminated(self) -> bool:
        return self._terminated

    def set_tag(self, key: str, value) -> None:
        self._write(self._client.set_tag, key, value, _MAX_TAG_CHARS)

    def log_param(self, key: str, value) -> None:
        self._write(self._client.log_param, key, value, _MAX_PARAM_CHARS)

    def terminate(self, status: str = "FINISHED") -> None:
        """Write the terminal status once; later calls are no-ops."""
        if self._terminated:
            return
        self._terminated = True
        try:
            self._client.set_terminated(self.run_id, status)
        except Exception as e:
            log.warning(f"[MCP] Could not terminate run {self.run_id}: {e}")

    def _write(self, fn, key: str, value, limit: int) -> None:
        # Observability writes never fail the run they describe.
        try:
            fn(self.run_id, key, str(value)[:limit])
        except Exception as e:
            log.debug(f"[MCP] Dropped {key} for run {self.run_id}: {e}")


def reconcile_orphaned_runs(experiment_names, live_run_ids,
                            client: MlflowClient = None) -> list:
    """Terminate RUNNING runs that no live task owns, returning their ids.

    A run only reaches a terminal status from the task that owns it, so a
    process killed mid-flight leaves its run RUNNING with a null end_time
    and History renders it as running forever. Called at boot, where the
    live cache is empty and every RUNNING row is by definition residue.
    """
    client = client or MlflowClient()
    experiment_ids = []
    for name in experiment_names:
        experiment = client.get_experiment_by_name(name)
        if experiment is not None:
            experiment_ids.append(experiment.experiment_id)
    if not experiment_ids:
        return []

    reconciled = []
    for run in client.search_runs(
        experiment_ids=experiment_ids,
        filter_string="attributes.status = 'RUNNING'",
    ):
        run_id = run.info.run_id
        if run_id in live_run_ids:
            continue
        try:
            client.set_tag(run_id, "mcp.reconciled", "orphaned")
            client.set_terminated(run_id, "KILLED")
            reconciled.append(run_id)
        except Exception as e:
            log.warning(f"[MCP] Could not reconcile orphaned run {run_id}: {e}")
    return reconciled
