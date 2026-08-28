"""Run lifecycle: one terminal status per run, written by its own task.

mlflow's fluent API keeps its active run on a thread-local stack, and every
/plugin/mcp/execute request is an asyncio task on one event-loop thread.
Concurrent runs therefore shared a single active-run pointer, which ended
each other's runs, wrote tags to the wrong run, and minted phantom runs
whenever the stack was empty.
"""
import asyncio

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from plugins.mcp.app.mlflow_run import (
    RunTracker,
    reconcile_orphaned_runs,
    resolve_experiment_id,
)

EXPERIMENT = "test-run-lifecycle"


@pytest.fixture
def client(tmp_path):
    """Isolated store, restored afterwards: mlflow's tracking URI and active
    experiment are process-global and leak into later test modules."""
    previous_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    yield MlflowClient()
    if mlflow.active_run():
        mlflow.end_run()
    mlflow.set_tracking_uri(previous_uri)


def _runs(client):
    return client.search_runs([resolve_experiment_id(EXPERIMENT, client)])


def test_start_does_not_activate_the_run(client):
    tracker = RunTracker.start(EXPERIMENT, "MCP Author")
    assert mlflow.active_run() is None
    assert client.get_run(tracker.run_id).info.status == "RUNNING"


def test_bind_reuses_an_existing_run(client):
    minted = RunTracker.start(EXPERIMENT, "MCP Author")
    assert RunTracker.bind(minted.run_id, EXPERIMENT, "other").run_id == minted.run_id
    assert len(_runs(client)) == 1


def test_terminate_is_written_once(client):
    tracker = RunTracker.start(EXPERIMENT, "MCP Author")
    tracker.terminate("FINISHED")
    tracker.terminate("FAILED")
    assert client.get_run(tracker.run_id).info.status == "FINISHED"


def test_writes_never_mint_a_phantom_run(client):
    """The defect: a fluent set_tag with an empty stack creates a new run."""
    tracker = RunTracker.start(EXPERIMENT, "MCP Author")
    tracker.set_tag("stage", "error")
    tracker.log_param("error", "boom")
    assert len(_runs(client)) == 1


def test_oversized_values_do_not_fail_the_run(client):
    tracker = RunTracker.start(EXPERIMENT, "MCP Author")
    tracker.set_tag("reasoning", "x" * 20000)
    tracker.log_param("result_summary", "y" * 20000)
    run = client.get_run(tracker.run_id)
    assert run.data.tags["reasoning"].startswith("x")
    assert run.data.params["result_summary"].startswith("y")


def test_concurrent_tasks_do_not_terminate_each_other(client):
    """Three overlapping runs, each ending only itself, as execute() does."""
    async def drive(index):
        tracker = RunTracker.start(EXPERIMENT, f"MCP Author {index}")
        tracker.set_tag("stage", "initializing")
        await asyncio.sleep(0.01 * (3 - index))
        tracker.set_tag("stage", "complete")
        tracker.terminate("FINISHED")
        return tracker.run_id

    async def overlap():
        return await asyncio.gather(*(drive(i) for i in range(3)))

    run_ids = asyncio.run(overlap())

    assert len(_runs(client)) == 3
    for run_id in run_ids:
        run = client.get_run(run_id)
        assert run.info.status == "FINISHED"
        assert run.info.end_time is not None
        assert run.data.tags["stage"] == "complete"


def test_fluent_end_run_is_what_stole_the_terminal_status(client):
    """Pins the mechanism so a revert to the fluent API fails here."""
    victim = RunTracker.start(EXPERIMENT, "victim")
    mlflow.set_experiment(EXPERIMENT)  # the fluent API refuses to resume without it
    mlflow.start_run(run_id=victim.run_id)
    mlflow.end_run()  # a second task's "ensure no active run"
    assert client.get_run(victim.run_id).info.status == "FINISHED"


def test_reconcile_terminates_orphans_not_in_the_live_cache(client):
    orphan = RunTracker.start(EXPERIMENT, "orphan")
    live = RunTracker.start(EXPERIMENT, "live")

    reconciled = reconcile_orphaned_runs([EXPERIMENT], {live.run_id})

    assert reconciled == [orphan.run_id]
    assert client.get_run(orphan.run_id).info.status == "KILLED"
    assert client.get_run(orphan.run_id).info.end_time is not None
    assert client.get_run(orphan.run_id).data.tags["mcp.reconciled"] == "orphaned"
    assert client.get_run(live.run_id).info.status == "RUNNING"


def test_reconcile_leaves_finished_runs_alone(client):
    tracker = RunTracker.start(EXPERIMENT, "done")
    tracker.terminate("FINISHED")

    assert reconcile_orphaned_runs([EXPERIMENT], set()) == []
    assert client.get_run(tracker.run_id).info.status == "FINISHED"


def test_reconcile_ignores_unknown_experiments(client):
    RunTracker.start(EXPERIMENT, "orphan")
    assert reconcile_orphaned_runs(["never-created"], set()) == []
    assert _runs(client)[0].info.status == "RUNNING"
