"""_run_execution owns exactly one MLflow run, start to terminal status.

Drives MCPService with stub workflows so the concurrency the aiohttp event
loop produces is reproduced without an LLM: three overlapping requests used
to end and retag each other's runs because mlflow's active-run stack is
shared per thread, and a failure with an empty stack minted a phantom run
instead of recording the error.
"""
import asyncio
import types

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from plugins.mcp.app import mcp_svc as mcp_svc_module
from plugins.mcp.app.mcp_svc import MCPService
from plugins.mcp.app.mlflow_run import RunTracker

EXPERIMENT = "test-run-execution"


def _workflow(workflow_id, run):
    return types.SimpleNamespace(
        id=workflow_id,
        display_name=workflow_id.title(),
        mlflow_experiment=EXPERIMENT,
        required_servers=[],
        optional_servers=[],
        accepted_capabilities=[],
        supports_chat_history=False,
        run=run,
    )


@pytest.fixture
def svc(tmp_path, monkeypatch):
    previous_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    monkeypatch.setattr(mcp_svc_module, "_SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(
        mcp_svc_module, "resolve_llm_config", lambda cfg: {"model": "gpt-4o-mini"}
    )
    service = MCPService(services={})
    yield service
    if mlflow.active_run():
        mlflow.end_run()
    mlflow.set_tracking_uri(previous_uri)


def _experiment_runs(client=None):
    client = client or MlflowClient()
    experiment = client.get_experiment_by_name(EXPERIMENT)
    return client.search_runs([experiment.experiment_id]) if experiment else []


def test_concurrent_runs_each_reach_their_own_terminal_status(svc):
    """The defect: overlapping requests shared one active-run pointer."""
    async def slow(prompt, lm_obj, run_id=None, **kwargs):
        await asyncio.sleep(0.05)
        return {"process_result": f"done {prompt}", "reasoning": "", "trajectory": {}}

    svc.workflow_registry = {"slow": _workflow("slow", slow)}

    async def three_at_once():
        started = [await svc.execute(workflow_id="slow", prompt=f"p{i}")
                   for i in range(3)]
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})
        return started

    started = asyncio.run(three_at_once())

    client = MlflowClient()
    assert len(_experiment_runs(client)) == 3
    for index, handle in enumerate(started):
        run = client.get_run(handle["run_id"])
        assert run.info.status == "FINISHED"
        assert run.info.end_time is not None
        assert run.data.params["prompt"] == f"p{index}"
        assert run.data.tags["stage"] == "complete"


def test_failure_is_recorded_on_the_failing_run(svc):
    """The defect: tagging with an empty stack minted an auto-named run."""
    async def boom(prompt, lm_obj, run_id=None, **kwargs):
        raise RuntimeError("workflow exploded")

    svc.workflow_registry = {"boom": _workflow("boom", boom)}

    async def once():
        handle = await svc.execute(workflow_id="boom", prompt="p")
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})
        return handle

    handle = asyncio.run(once())

    runs = _experiment_runs()
    assert len(runs) == 1
    run = runs[0]
    assert run.info.run_id == handle["run_id"]
    assert run.info.status == "FAILED"
    assert run.data.tags["stage"] == "error"
    assert run.data.params["error"] == "workflow exploded"


def test_model_param_is_logged_for_the_history_column(svc):
    """History's Model column reads params.model, which nothing wrote."""
    async def noop(prompt, lm_obj, run_id=None, **kwargs):
        return {"process_result": "ok"}

    svc.workflow_registry = {"noop": _workflow("noop", noop)}

    async def once():
        handle = await svc.execute(workflow_id="noop", prompt="p")
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})
        return handle

    handle = asyncio.run(once())
    assert MlflowClient().get_run(handle["run_id"]).data.params["model"] == "gpt-4o-mini"


def test_reconcile_kills_runs_stranded_by_a_dead_process(svc):
    svc.workflow_registry = {"noop": _workflow("noop", None)}
    stranded = RunTracker.start(EXPERIMENT, "MCP Noop").run_id

    reconciled = asyncio.run(svc.reconcile_orphaned_runs())

    assert reconciled == [stranded]
    assert MlflowClient().get_run(stranded).info.status == "KILLED"


def test_reconcile_spares_runs_the_live_cache_still_owns(svc):
    svc.workflow_registry = {"noop": _workflow("noop", None)}
    in_flight = RunTracker.start(EXPERIMENT, "MCP Noop").run_id
    svc._record_run(in_flight, {"status": "RUNNING"})

    assert asyncio.run(svc.reconcile_orphaned_runs()) == []
    assert MlflowClient().get_run(in_flight).info.status == "RUNNING"
