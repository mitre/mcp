"""Whoever owns a run's lifecycle owns writing its terminal state.

Observed in the field: pressing Stop on a Plan-and-Execute run tore down the
MCP stdio transport, and anyio surfaced that as

    ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
      +-- anyio.BrokenResourceError

with no CancelledError leaf anywhere in it. A workflow cannot tell that from
a genuine crash, but its `except Exception` ran full failure bookkeeping
before re-raising -- printing a traceback that read as a server fault and,
worse, calling log_param("error"/"traceback"). MLflow params are immutable,
so the service's later KILLED tags could not take them back and History
showed a deliberate stop as an error.

The service knows the difference, because it records the intent in
_cancelling before it cancels. So a workflow handed a run by the orchestrator
now re-raises and lets the orchestrator classify; only a workflow that minted
its own run writes that run's failure state.
"""
import asyncio
import logging
import types

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from plugins.mcp.app.workflows import author, plan_execute
from plugins.mcp.app.mlflow_run import RunTracker

# The shape anyio actually produced, reproduced exactly: an Exception (so the
# workflow's `except Exception` catches it) carrying no cancellation leaf.
def _torn_down_transport():
    return ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [RuntimeError("anyio.BrokenResourceError")],
    )


class _ExplodingStack:
    """Stands in for AsyncExitStack, the first thing inside the try block."""

    async def __aenter__(self):
        raise _torn_down_transport()

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture(params=[plan_execute, author], ids=["plan_execute", "author"])
def workflow(request, tmp_path, monkeypatch):
    """Both workflows carry the same handler, so both are held to it."""
    previous_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    monkeypatch.setattr(
        request.param, "AsyncExitStack", lambda *a, **k: _ExplodingStack()
    )
    yield request.param
    if mlflow.active_run():
        mlflow.end_run()
    mlflow.set_tracking_uri(previous_uri)


# Enough config to clear each workflow's credential guard, which fires
# before the try block and is a genuine failure, not the case under test.
_LM = {
    "model": "openai/gpt-4o-mini",
    "api_key": "sk-test",
    "api_base": "http://localhost:1",
}


def _service_workflow(workflow_id, run):
    """Registry entry shaped the way MCPService expects."""
    return types.SimpleNamespace(
        id=workflow_id, display_name=workflow_id.title(),
        mlflow_experiment="test-failure-logging", required_servers=[],
        optional_servers=[], accepted_capabilities=[],
        supports_chat_history=False, run=run,
    )


@pytest.fixture
def svc_logs(tmp_path, monkeypatch):
    """MCPService wired to a temp store, plus a helper that drives one run."""
    from plugins.mcp.app import mcp_svc as mcp_svc_module
    from plugins.mcp.app.mcp_svc import MCPService

    previous_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/logs.db")
    monkeypatch.setattr(mcp_svc_module, "_SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(
        mcp_svc_module, "resolve_llm_config", lambda cfg: {"model": "gpt-4o-mini"}
    )
    service = MCPService(services={})

    def drive(workflow_id):
        async def once():
            await service.execute(workflow_id=workflow_id, prompt="p")
            await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})
        asyncio.run(once())

    yield service, drive
    if mlflow.active_run():
        mlflow.end_run()
    mlflow.set_tracking_uri(previous_uri)


def _drive(module, run_id):
    with pytest.raises(BaseException):
        asyncio.run(module.run("test", lm_obj=dict(_LM), run_id=run_id))


def test_an_orchestrated_run_is_left_for_the_orchestrator_to_classify(workflow):
    """The bug: a stopped run kept an immutable error param naming a crash."""
    owner = RunTracker.start(workflow._MLFLOW_EXPERIMENT, "orchestrated")

    _drive(workflow, owner.run_id)

    run = MlflowClient().get_run(owner.run_id)
    assert "error" not in run.data.params
    assert "traceback" not in run.data.params
    # Still open: the orchestrator terminates the run it handed out, and it
    # is the layer that decides whether this was KILLED or FAILED.
    assert run.info.status == "RUNNING"


def test_a_run_the_workflow_minted_is_still_the_workflow_to_close(workflow):
    """Standalone use has no orchestrator, so the handler must stay."""
    before = {r.info.run_id for r in _experiment_runs(workflow)}

    _drive(workflow, None)

    minted = [r for r in _experiment_runs(workflow) if r.info.run_id not in before]
    assert len(minted) == 1
    run = minted[0]
    assert run.info.status == "FAILED"
    assert "BrokenResourceError" in run.data.params["error"]
    assert "traceback" in run.data.params


def _experiment_runs(module):
    client = MlflowClient()
    experiment = client.get_experiment_by_name(module._MLFLOW_EXPERIMENT)
    return client.search_runs([experiment.experiment_id]) if experiment else []


def test_a_genuine_failure_puts_its_stack_on_the_console(svc_logs, caplog):
    """Workflows stopped printing it, so the service has to.

    The MLflow traceback param is best-effort (RunTracker._write swallows a
    dead tracking store), so exc_info here is the only copy an operator is
    guaranteed to see.
    """
    svc, drive = svc_logs

    async def boom(prompt, lm_obj, run_id=None, **kwargs):
        raise RuntimeError("workflow exploded")

    svc.workflow_registry = {"boom": _service_workflow("boom", boom)}
    with caplog.at_level(logging.ERROR, logger="plugins.mcp"):
        drive("boom")

    failures = [r for r in caplog.records if "Execution failed" in r.getMessage()]
    assert failures, "no failure logged at ERROR"
    assert failures[0].exc_info is not None
    assert "RuntimeError: workflow exploded" in caplog.text


def test_a_stopped_run_logs_no_stack(svc_logs, caplog):
    """The cancel path returns above the failure branch; keep it that way."""
    svc, _ = svc_logs

    async def slow(prompt, lm_obj, run_id=None, **kwargs):
        await asyncio.sleep(3600)

    svc.workflow_registry = {"slow": _service_workflow("slow", slow)}

    async def start_then_stop():
        handle = await svc.execute(workflow_id="slow", prompt="p")
        await asyncio.sleep(0)
        svc.cancel_run(handle["run_id"])
        for _ in range(6):
            await asyncio.sleep(0)

    with caplog.at_level(logging.ERROR, logger="plugins.mcp"):
        asyncio.run(start_then_stop())

    assert not [r for r in caplog.records if "Execution failed" in r.getMessage()]
