"""Stage transitions a workflow reports have to reach the polling UI.

The defect: workflows report progress with tracker.set_tag("stage", ...),
which writes to MLflow only, while /status serves MCPService._runs. The
cached snapshot was written twice per run -- "initializing" at the top of
_run_execution and a terminal value at the bottom -- so the chat UI's stage
line read "initializing" for the whole run no matter how many stages the
workflow announced.

A workflow also binds its OWN RunTracker to the run id the service started,
so the mirror has to follow the run rather than one tracker instance.
"""
import asyncio
import types

import mlflow
import pytest

from plugins.mcp.app import mcp_svc as mcp_svc_module
from plugins.mcp.app.mcp_svc import MCPService
from plugins.mcp.app.mlflow_run import RunTracker, _stage_observers

EXPERIMENT = "test-run-stage-progress"


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


def _drive(svc, workflow_id, prompt="p"):
    async def once():
        handle = await svc.execute(workflow_id=workflow_id, prompt=prompt)
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})
        return handle

    return asyncio.run(once())


def test_a_stage_a_workflow_reports_reaches_the_polled_snapshot(svc):
    """The bug: /status served "initializing" for the life of the run."""
    seen = []

    async def staged(prompt, lm_obj, run_id=None, **kwargs):
        # Exactly what the real workflows do: bind a fresh tracker to the
        # run the service already started, then tag progress through it.
        tracker = RunTracker.bind(run_id, EXPERIMENT, "staged")
        for stage in ("listing tools", "creating DSPy ReAct instance"):
            tracker.set_tag("stage", stage)
            seen.append(svc.get_run(run_id)["stage"])
        return {"process_result": "ok", "reasoning": "", "trajectory": {}}

    svc.workflow_registry = {"staged": _workflow("staged", staged)}
    _drive(svc, "staged")

    assert seen == ["listing tools", "creating DSPy ReAct instance"]


def test_the_terminal_stage_still_wins(svc):
    """A run that finished must not be left showing its last live stage."""
    async def staged(prompt, lm_obj, run_id=None, **kwargs):
        RunTracker.bind(run_id, EXPERIMENT, "staged").set_tag("stage", "executing")
        return {"process_result": "ok", "reasoning": "", "trajectory": {}}

    svc.workflow_registry = {"staged": _workflow("staged", staged)}
    handle = _drive(svc, "staged")

    assert svc.get_run(handle["run_id"])["stage"] == "complete"


def test_a_late_stage_tag_cannot_reopen_a_terminal_snapshot(svc):
    """Guarded on RUNNING: a stray tag must not overwrite a final stage."""
    async def noop(prompt, lm_obj, run_id=None, **kwargs):
        return {"process_result": "ok", "reasoning": "", "trajectory": {}}

    svc.workflow_registry = {"noop": _workflow("noop", noop)}
    handle = _drive(svc, "noop")
    run_id = handle["run_id"]

    svc._update_stage(run_id, "listing tools")

    assert svc.get_run(run_id)["stage"] == "complete"


def test_the_observer_is_released_when_the_run_ends(svc):
    """Registered per run; leaking one would pin the service per request."""
    async def noop(prompt, lm_obj, run_id=None, **kwargs):
        return {"process_result": "ok", "reasoning": "", "trajectory": {}}

    svc.workflow_registry = {"noop": _workflow("noop", noop)}
    handle = _drive(svc, "noop")

    assert handle["run_id"] not in _stage_observers


def test_a_failed_run_releases_its_observer_too(svc):
    """The finally has to run on the error path, not just the happy one."""
    async def boom(prompt, lm_obj, run_id=None, **kwargs):
        raise RuntimeError("workflow exploded")

    svc.workflow_registry = {"boom": _workflow("boom", boom)}
    handle = _drive(svc, "boom")

    assert handle["run_id"] not in _stage_observers
    assert svc.get_run(handle["run_id"])["stage"] == "error"


def test_concurrent_runs_do_not_cross_stages(svc):
    """Keyed by run id, so one run's progress cannot land on another's."""
    async def staged(prompt, lm_obj, run_id=None, **kwargs):
        tracker = RunTracker.bind(run_id, EXPERIMENT, "staged")
        tracker.set_tag("stage", f"working on {prompt}")
        # Hold both runs open at once so the observers genuinely overlap.
        await asyncio.sleep(0.05)
        return {"process_result": "ok", "reasoning": "", "trajectory": {}}

    svc.workflow_registry = {"staged": _workflow("staged", staged)}

    async def two_at_once():
        handles = [await svc.execute(workflow_id="staged", prompt=f"p{i}")
                   for i in range(2)]
        # Sampled mid-flight: after this sleep both workflows have tagged
        # their stage but neither has returned.
        await asyncio.sleep(0.02)
        sampled = [svc.get_run(h["run_id"])["stage"] for h in handles]
        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})
        return sampled

    assert asyncio.run(two_at_once()) == ["working on p0", "working on p1"]


def test_a_tracker_for_an_unregistered_run_is_harmless(svc):
    """Trackers outlive runs (the cancel path builds one); no KeyError."""
    RunTracker(run_id="never-registered").set_tag("stage", "orphan")
