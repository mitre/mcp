"""MLflow must not outlive the process that started it.

Caldera has no plugin teardown hook, so a Popen with no cleanup is reparented
to init and holds the port across every restart. It must also never stop a
server the operator is running themselves.

Adoption is the other half: a bare TCP connect proved only that something
answered on the port, so a non-MLflow listener made every run fail at
create_run, and another tree's server took our runs into its store and
killed that tree's live runs at the next boot reconcile.
"""
import logging
import os
import subprocess

import pytest

from plugins.mcp import hook


class _FakeProc:
    def __init__(self, running=True):
        self.running = running
        self.terminated = self.killed = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


@pytest.fixture(autouse=True)
def _reset():
    yield
    hook._mlflow_proc = None


def test_it_stops_the_server_it_started():
    hook._mlflow_proc = proc = _FakeProc()
    hook._stop_mlflow_server()
    assert proc.terminated


def test_it_does_nothing_when_it_started_nothing():
    # The port was already open, so the server belongs to the operator.
    hook._mlflow_proc = None
    hook._stop_mlflow_server()


def test_it_does_not_re_terminate_a_dead_child():
    hook._mlflow_proc = proc = _FakeProc(running=False)
    hook._stop_mlflow_server()
    assert not proc.terminated


def test_a_child_ignoring_terminate_is_killed(monkeypatch):
    proc = _FakeProc()
    def _hang(timeout=None):
        raise subprocess.TimeoutExpired(cmd="mlflow", timeout=timeout)
    monkeypatch.setattr(proc, "wait", _hang)
    hook._mlflow_proc = proc
    hook._stop_mlflow_server()
    assert proc.killed


def _no_spawn(monkeypatch, why):
    monkeypatch.setattr(hook, "_start_mlflow_server",
                        lambda: pytest.fail(why))


def test_our_own_running_server_is_adopted(monkeypatch):
    monkeypatch.setattr(hook, "is_port_open", lambda *a, **k: True)
    monkeypatch.setattr(hook, "_probe_listener",
                        lambda *a, **k: os.path.join(hook._MLFLOW_ARTIFACT_ROOT, "0"))
    _no_spawn(monkeypatch, "spawned over our own running server")
    monkeypatch.setattr(hook, "_reclaim_port", lambda: pytest.fail("killed our own server"))
    hook._ensure_mlflow_server()


def test_a_listener_that_is_not_mlflow_is_neither_adopted_nor_killed(monkeypatch, caplog):
    # macOS binds :5000 to AirPlay Receiver, and adopting it made every
    # create_run fail with a 403.
    monkeypatch.setattr(hook, "is_port_open", lambda *a, **k: True)
    monkeypatch.setattr(hook, "_probe_listener", lambda *a, **k: None)
    _no_spawn(monkeypatch, "spawned onto an occupied port")
    monkeypatch.setattr(hook, "_reclaim_port", lambda: pytest.fail("killed an unidentified process"))
    with caplog.at_level(logging.ERROR, logger=hook.log.name):
        hook._ensure_mlflow_server()
    # Silent adoption was the defect: not spawning is not enough, the
    # operator has to be told why their runs are about to fail.
    assert "not MLflow" in caplog.text


def test_another_trees_server_is_reclaimed_and_restarted(monkeypatch):
    monkeypatch.setattr(hook, "is_port_open", lambda *a, **k: True)
    monkeypatch.setattr(hook, "_probe_listener", lambda *a, **k: "/somewhere/else/mlruns/0")
    started = []
    monkeypatch.setattr(hook, "_reclaim_port", lambda: True)
    monkeypatch.setattr(hook, "_start_mlflow_server", lambda: started.append(True))
    hook._ensure_mlflow_server()
    assert started


def test_a_foreign_server_that_will_not_die_is_not_written_to(monkeypatch, caplog):
    monkeypatch.setattr(hook, "is_port_open", lambda *a, **k: True)
    monkeypatch.setattr(hook, "_probe_listener", lambda *a, **k: "/somewhere/else/mlruns/0")
    monkeypatch.setattr(hook, "_reclaim_port", lambda: False)
    _no_spawn(monkeypatch, "spawned onto a port still held by another server")
    with caplog.at_level(logging.ERROR, logger=hook.log.name):
        hook._ensure_mlflow_server()
    assert "Could not free" in caplog.text


@pytest.mark.parametrize("artifact_root, ours", [
    ("", False),
    ("/somewhere/else/mlruns/0", False),
    ("mlflow-artifacts:/0", False),
])
def test_a_foreign_artifact_root_is_not_ours(artifact_root, ours):
    assert hook._serves_our_store(artifact_root) is ours


@pytest.mark.parametrize("prefix", ["", "file://"])
def test_our_artifact_root_is_ours(prefix):
    assert hook._serves_our_store(prefix + os.path.join(hook._MLFLOW_ARTIFACT_ROOT, "0"))


@pytest.mark.parametrize("cmdline, port", [
    (["mlflow", "server", "--port", "5050"], 5050),
    (["/venv/bin/mlflow", "ui", "--port", "5050"], 5050),
    # mlflow's own default, which is what an operator typing `mlflow ui` gets.
    (["mlflow", "server"], 5000),
    # The uvicorn workers carry the port too, but the CLI parent owns them.
    (["python", "-m", "uvicorn", "--port", "5050", "mlflow.server.fastapi_app:app"], None),
    (["python", "server.py", "--port", "5050"], None),
    (["mlflow", "server", "--port", "not-a-port"], None),
])
def test_only_an_mlflow_cli_on_our_port_is_a_reclaim_candidate(cmdline, port):
    assert hook._mlflow_server_port(cmdline) == port


class _ReconcileRecorder:
    def __init__(self):
        self.calls = 0

    async def reconcile_orphaned_runs(self):
        self.calls += 1


def _bring_up(monkeypatch, artifact_root, spawned=False):
    import asyncio
    monkeypatch.setattr(hook, "_ensure_mlflow_server", lambda: spawned)
    monkeypatch.setattr(hook, "is_port_open", lambda *a, **k: True)
    monkeypatch.setattr(hook, "_probe_listener", lambda *a, **k: artifact_root)
    svc = _ReconcileRecorder()
    asyncio.run(hook._bring_up_tracking(svc))
    return svc.calls


def test_boot_reconcile_runs_against_our_own_store(monkeypatch):
    assert _bring_up(monkeypatch, os.path.join(hook._MLFLOW_ARTIFACT_ROOT, "0")) == 1


def test_boot_reconcile_never_touches_a_foreign_store(monkeypatch):
    # Reconciling another tree's server would mark its live runs KILLED.
    assert _bring_up(monkeypatch, "/somewhere/else/mlruns/0") == 0
    assert _bring_up(monkeypatch, None) == 0


def test_a_failed_bring_up_is_logged_not_raised(monkeypatch, caplog):
    import asyncio

    def _boom():
        raise OSError("no mlflow here")

    monkeypatch.setattr(hook, "_ensure_mlflow_server", _boom)
    svc = _ReconcileRecorder()
    with caplog.at_level(logging.ERROR, logger=hook.log.name):
        asyncio.run(hook._bring_up_tracking(svc))
    assert "Failed to start MLflow server" in caplog.text
    assert svc.calls == 0


def test_a_spawn_does_not_block_and_ensure_reports_it(monkeypatch):
    monkeypatch.setattr(hook, "is_port_open", lambda *a, **k: False)
    started = []
    monkeypatch.setattr(hook, "_start_mlflow_server", lambda: started.append(True))
    assert hook._ensure_mlflow_server() is True
    assert started


def test_the_mlflow_http_client_is_bounded():
    # Unbounded, MLflow retries a sick server for minutes on the event loop.
    assert os.environ.get("MLFLOW_HTTP_REQUEST_TIMEOUT")
    assert os.environ.get("MLFLOW_HTTP_REQUEST_MAX_RETRIES")


def test_importing_the_hook_leaves_root_logging_alone():
    # basicConfig at import took over the whole server's log handlers.
    assert any(isinstance(h, logging.NullHandler)
               for h in logging.getLogger("plugins.mcp").handlers)
    with open(hook.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert "logging.basicConfig(" not in source
