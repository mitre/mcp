"""Stopping one in-flight run leaves it KILLED and leaves the others alone.

A bare task.cancel() is worse than no Stop button: CancelledError is a
BaseException, so the `except Exception` arm misses it while the finally still
writes FAILED, and the run cache stays RUNNING forever with the page locked
behind it. anyio makes it worse by repackaging a cancel that lands during MCP
session startup as an ExceptionGroup, which `except Exception` does catch.
Both shapes are driven here.
"""
import asyncio
import json
import types

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from plugins.mcp.app import mcp_svc as mcp_svc_module
from plugins.mcp.app.mcp_svc import MCPService

EXPERIMENT = "test-run-cancellation"


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


async def _forever(prompt, lm_obj, run_id=None, **kwargs):
    await asyncio.sleep(3600)


async def _settle():
    """Let every background run task finish unwinding."""
    await asyncio.gather(
        *(asyncio.all_tasks() - {asyncio.current_task()}), return_exceptions=True
    )


def test_cancel_leaves_the_run_killed_not_failed(svc):
    """The defect: FAILED in MLflow, RUNNING in the cache, page locked."""
    svc.workflow_registry = {"hang": _workflow("hang", _forever)}

    async def start_then_stop():
        handle = await svc.execute(workflow_id="hang", prompt="p")
        await asyncio.sleep(0)
        assert svc.cancel_run(handle["run_id"]) is True
        await _settle()
        return handle

    handle = asyncio.run(start_then_stop())
    run_id = handle["run_id"]

    snapshot = svc.get_run(run_id)
    assert snapshot["status"] == "KILLED"
    assert snapshot["stage"] == "stopped by user"
    # The bubble heading already says it stopped; this line says what remains.
    assert snapshot["error"].startswith("Anything already created in CALDERA stays")
    assert "operation" in snapshot["error"]

    run = MlflowClient().get_run(run_id)
    assert run.info.status == "KILLED"
    assert run.info.end_time is not None
    assert run.data.tags["mcp.cancelled"] == "user"


def test_a_stopped_run_is_not_left_carrying_an_error_param(svc):
    """The service must not route a cancel through its failure branch.

    Covers the service half only; the workflow half of this bug lives in
    tests/test_workflow_failure_ownership.py. The exception here is the
    shape anyio really produced when Stop tore down the MCP stdio
    transport: an ExceptionGroup wrapping BrokenResourceError with no
    CancelledError leaf, so the type alone cannot identify the cancel.
    """
    async def transport_torn_down(prompt, lm_obj, run_id=None, **kwargs):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # No CancelledError leaf: exactly what anyio hands back.
            raise ExceptionGroup(
                "unhandled errors in a TaskGroup", [RuntimeError("BrokenResourceError")]
            )

    svc.workflow_registry = {"torn": _workflow("torn", transport_torn_down)}

    async def start_then_stop():
        handle = await svc.execute(workflow_id="torn", prompt="p")
        await asyncio.sleep(0)
        svc.cancel_run(handle["run_id"])
        await _settle()
        return handle

    handle = asyncio.run(start_then_stop())
    run = MlflowClient().get_run(handle["run_id"])

    assert run.info.status == "KILLED"
    assert run.data.tags["mcp.cancelled"] == "user"
    # The whole point: History must not show this as an error.
    assert "error" not in run.data.params
    assert "traceback" not in run.data.params


def test_a_genuine_failure_still_records_its_traceback(svc):
    """Moving the param must not cost real failures their diagnosis."""
    async def boom(prompt, lm_obj, run_id=None, **kwargs):
        raise RuntimeError("workflow exploded")

    svc.workflow_registry = {"boom": _workflow("boom", boom)}

    async def once():
        handle = await svc.execute(workflow_id="boom", prompt="p")
        await _settle()
        return handle

    handle = asyncio.run(once())
    run = MlflowClient().get_run(handle["run_id"])

    assert run.info.status == "FAILED"
    assert run.data.params["error"] == "workflow exploded"
    assert "RuntimeError: workflow exploded" in run.data.params["traceback"]


def test_cancel_wrapped_in_an_exception_group_is_still_a_stop(svc):
    """anyio hands an early cancel back as an ExceptionGroup, an Exception."""
    async def anyio_shaped(prompt, lm_obj, run_id=None, **kwargs):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise ExceptionGroup("unhandled errors in a TaskGroup", [RuntimeError("closed")])

    svc.workflow_registry = {"wrapped": _workflow("wrapped", anyio_shaped)}

    async def start_then_stop():
        handle = await svc.execute(workflow_id="wrapped", prompt="p")
        await asyncio.sleep(0)
        svc.cancel_run(handle["run_id"])
        await _settle()
        return handle

    handle = asyncio.run(start_then_stop())

    assert svc.get_run(handle["run_id"])["status"] == "KILLED"
    run = MlflowClient().get_run(handle["run_id"])
    assert run.info.status == "KILLED"
    assert run.data.tags["mcp.cancelled"] == "user"


def test_cancel_names_one_run_and_spares_the_others(svc):
    svc.workflow_registry = {"hang": _workflow("hang", _forever)}

    async def start_two_stop_one():
        doomed = await svc.execute(workflow_id="hang", prompt="doomed")
        spared = await svc.execute(workflow_id="hang", prompt="spared")
        await asyncio.sleep(0)
        svc.cancel_run(doomed["run_id"])
        # Only the cancelled task should unwind; the other is still sleeping.
        await asyncio.sleep(0.05)
        # Read inside the loop: asyncio.run() cancels what is left on exit.
        return svc.get_run(doomed["run_id"]), svc.get_run(spared["run_id"])

    doomed, spared = asyncio.run(start_two_stop_one())

    assert doomed["status"] == "KILLED"
    assert spared["status"] == "RUNNING"


def test_a_shutdown_cancel_is_not_reported_as_a_user_stop(svc):
    """Loop teardown cancels in-flight tasks; nobody pressed Stop."""
    svc.workflow_registry = {"hang": _workflow("hang", _forever)}

    async def start_and_walk_away():
        handle = await svc.execute(workflow_id="hang", prompt="p")
        await asyncio.sleep(0)
        return handle

    # asyncio.run() cancels the still-sleeping run task as it closes the loop.
    handle = asyncio.run(start_and_walk_away())

    assert svc.get_run(handle["run_id"])["status"] == "KILLED"
    run = MlflowClient().get_run(handle["run_id"])
    assert run.info.status == "KILLED"
    assert run.data.tags["mcp.cancelled"] == "server"


def test_a_cancel_before_the_task_body_runs_still_closes_the_run(svc):
    """Nothing recorded it, so nothing else would ever move it off RUNNING."""
    svc.workflow_registry = {"hang": _workflow("hang", _forever)}

    async def stop_before_it_starts():
        handle = await svc.execute(workflow_id="hang", prompt="p")
        # No sleep(0): the task exists but has never been scheduled.
        assert svc.cancel_run(handle["run_id"]) is True
        await _settle()
        return handle

    handle = asyncio.run(stop_before_it_starts())

    assert svc.get_run(handle["run_id"])["status"] == "KILLED"
    run = MlflowClient().get_run(handle["run_id"])
    assert run.info.status == "KILLED"
    assert run.data.tags["mcp.cancelled"] == "user"


def test_cancelling_twice_or_after_the_run_ended_is_harmless(svc):
    async def quick(prompt, lm_obj, run_id=None, **kwargs):
        return {"process_result": "done"}

    svc.workflow_registry = {
        "hang": _workflow("hang", _forever),
        "quick": _workflow("quick", quick),
    }

    async def scenario():
        hung = await svc.execute(workflow_id="hang", prompt="p")
        await asyncio.sleep(0)
        first = svc.cancel_run(hung["run_id"])
        second = svc.cancel_run(hung["run_id"])
        await _settle()
        third = svc.cancel_run(hung["run_id"])

        done = await svc.execute(workflow_id="quick", prompt="p")
        await _settle()
        after_finish = svc.cancel_run(done["run_id"])
        return first, second, third, after_finish, done

    first, second, third, after_finish, done = asyncio.run(scenario())

    assert first is True
    # Already cancelling, already over, and never ours: all no-ops.
    assert (second, third, after_finish) == (True, False, False)
    assert svc.get_run(done["run_id"])["status"] == "FINISHED"
    assert MlflowClient().get_run(done["run_id"]).info.status == "FINISHED"


def test_the_task_registry_empties_itself(svc):
    """It is not the LRU run cache; nothing else evicts it."""
    async def quick(prompt, lm_obj, run_id=None, **kwargs):
        return {"process_result": "done"}

    svc.workflow_registry = {"quick": _workflow("quick", quick)}

    async def once():
        await svc.execute(workflow_id="quick", prompt="p")
        await _settle()

    asyncio.run(once())
    assert svc._tasks == {}


class _FakeRequest:
    """Not a web_request.Request, so check_authorization stands aside."""

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        if self._payload is _NOT_JSON:
            raise ValueError("not json")
        return self._payload


_NOT_JSON = object()


class _StubService:
    def __init__(self, cancellable, snapshot=None):
        self._cancellable = cancellable
        self._snapshot = snapshot
        self.asked = []

    def cancel_run(self, run_id):
        self.asked.append(run_id)
        return self._cancellable

    def get_run(self, run_id):
        return self._snapshot


def _api(svc):
    from plugins.mcp.app import mcp_api
    return mcp_api.McpAPI({"mcp_svc": svc})


async def _cancel(svc, payload):
    resp = await _api(svc).cancel(_FakeRequest(payload))
    return resp.status, json.loads(resp.body.decode())


class TestCancelEndpoint:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [_NOT_JSON, ["run_id"], {}, {"run_id": ""}, {"run_id": ["a"]}],
    )
    async def test_a_body_without_a_run_id_is_refused(self, payload):
        svc = _StubService(cancellable=True)
        status, _ = await _cancel(svc, payload)
        assert status == 400
        assert svc.asked == []

    @pytest.mark.asyncio
    async def test_a_live_run_is_asked_to_stop(self):
        svc = _StubService(cancellable=True, snapshot={"status": "RUNNING"})
        status, body = await _cancel(svc, {"run_id": "abc"})
        assert (status, svc.asked) == (200, ["abc"])
        assert body == {"run_id": "abc", "cancelling": True, "status": "RUNNING"}

    @pytest.mark.asyncio
    async def test_a_run_nothing_owns_answers_200_not_an_error(self):
        """Pressing Stop twice, or after the run ended, must not look broken."""
        svc = _StubService(cancellable=False)
        status, body = await _cancel(svc, {"run_id": "abc"})
        assert status == 200
        assert body == {"run_id": "abc", "cancelling": False, "status": "UNKNOWN"}
