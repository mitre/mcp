"""author.run() must reject incomplete credentials before spawning servers.

The check sits above the AsyncExitStack, so a missing value fails fast
instead of after every MCP stdio subprocess has already been started.
"""
import pytest


@pytest.fixture
def offline_mlflow(tmp_path, monkeypatch):
    """Local sqlite store; the error path logs to MLflow before it raises."""
    import mlflow
    from plugins.mcp.app.workflows import author

    monkeypatch.setattr(author, "_ensure_mlflow", lambda: None)
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    mlflow.set_experiment("test-author-guards")
    yield
    if mlflow.active_run():
        mlflow.end_run()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing,lm_obj", [
    ("api_base", {"api_key": "sk-test", "model": "openai/x"}),
    ("api_key", {"api_base": "https://gw/v1", "model": "openai/x"}),
])
async def test_rejects_incomplete_credentials(offline_mlflow, missing, lm_obj, monkeypatch):
    from plugins.mcp.app.workflows import author

    # Fails loudly if the guard ever moves below the exit stack.
    def _no_spawn(*args, **kwargs):
        raise AssertionError("spawned a subprocess before validating credentials")

    monkeypatch.setattr(author, "stdio_client", _no_spawn, raising=False)

    with pytest.raises(ValueError, match=missing):
        await author.run("test", lm_obj=lm_obj, server_registry={}, enabled_servers=[])


@pytest.mark.asyncio
async def test_both_workflows_configure_from_separate_tasks(tmp_path):
    """mcp_svc runs each /execute in its own task.

    mlflow.dspy.autolog calls dspy.settings.configure, which pins ownership to
    the first asyncio task to reach it. Deferring it into run() therefore broke
    whichever workflow ran second, permanently, for the life of the process.
    """
    import asyncio
    import mlflow
    from plugins.mcp.app.workflows import author, plan_execute

    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    for module in (author, plan_execute):
        await asyncio.create_task(_configure(module))


async def _configure(module):
    module._ensure_mlflow()
