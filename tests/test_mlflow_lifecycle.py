"""MLflow must not outlive the process that started it.

Caldera has no plugin teardown hook, so a Popen with no cleanup is reparented
to init and holds the port across every restart. It must also never stop a
server the operator is running themselves.
"""
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


def test_an_already_running_server_is_left_alone(monkeypatch):
    monkeypatch.setattr(hook, "is_port_open", lambda *a, **k: True)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("spawned over a running server"))
    hook._mlflow_proc = None
    hook._ensure_mlflow_server()
    assert hook._mlflow_proc is None
