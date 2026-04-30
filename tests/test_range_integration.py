"""Verifies the RANGE plugin is properly wired into the MCP plugin.

Three layers, each runnable independently:
  1. discovery   — server_registry picks up range/mcp_server.py + MCP_METADATA
  2. spawn       — range/mcp_server.py boots as a stdio subprocess and lists tools
  3. multi-merge — factory client merges caldera_core + range tools w/o collision

Layers 1-2 need only the venv. Layer 3 calls into mcp_factory_client.run()
without invoking the LLM (it asserts on session/tool wiring before any
react.acall).

Run from the repo root:
    pytest plugins/mcp/tests/test_range_integration.py -v
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGINS_ROOT = REPO_ROOT / "plugins"
RANGE_SERVER = PLUGINS_ROOT / "range" / "mcp_server.py"
CORE_SERVER = PLUGINS_ROOT / "mcp" / "app" / "mcp_server.py"
VENV_PY = sys.executable

# Make the MCP plugin importable for layer 3
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---- Layer 1: discovery -------------------------------------------------

def test_discovery_finds_range_server():
    from plugins.mcp.app.discovery.servers import discover_mcp_servers

    registry = discover_mcp_servers(PLUGINS_ROOT)
    assert "caldera_core" in registry
    assert "range" in registry, (
        f"range plugin not discovered. Registry keys: {list(registry)}"
    )

    range_entry = registry["range"]
    assert range_entry["path"] == RANGE_SERVER
    metadata = range_entry["metadata"]
    assert metadata["display_name"] == "RANGE"
    assert metadata["default_enabled"] is False
    assert "Cyber range" in metadata["description"]


def test_metadata_parsed_without_executing_module():
    """server_registry uses ast.literal_eval so it must not crash even
    if the range plugin's runtime deps aren't installed in the parent."""
    from plugins.mcp.app.discovery.servers import _safe_load_metadata

    md = _safe_load_metadata(RANGE_SERVER)
    assert md is not None
    assert md.get("display_name") == "RANGE"


# ---- Layer 2: subprocess spawn -----------------------------------------

@pytest.mark.asyncio
async def test_range_server_spawns_and_lists_tools():
    """Boot range/mcp_server.py over stdio and assert it exposes its tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = os.environ.copy()
    # Tools call Caldera lazily, so listing doesn't require it to be up.
    env.setdefault("CALDERA_URL", "http://localhost:8888/api/v2/")
    env.setdefault("CORE_CALDERA_API_KEY", "ADMIN123")

    params = StdioServerParameters(
        command=VENV_PY, args=[str(RANGE_SERVER)], env=env
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools

    names = [t.name for t in tools]
    assert names, "range MCP server exposed zero tools"
    assert all(n.startswith("range_") for n in names), (
        f"range tools must be range_-prefixed to avoid collisions: {names}"
    )
    # Spot-check a couple known ones so a future rename can't silently
    # leave the test passing on an empty/mocked tool set.
    for required in ("range_inventory", "range_vm_deploy"):
        assert required in names, f"missing expected tool '{required}'"


# ---- Layer 3: multi-server merge in the factory client ------------------

@pytest.mark.asyncio
async def test_factory_client_merges_core_and_range_tools(monkeypatch):
    """mcp_factory_client.run() must spawn both servers and merge tools
    with zero name collisions. We short-circuit before the LLM call so
    no API key is needed."""
    from mcp import StdioServerParameters

    # Make the subprocess use the venv python regardless of $PATH
    orig_init = StdioServerParameters.__init__

    def patched_init(self, *a, **k):
        if k.get("command") == "python":
            k["command"] = VENV_PY
        orig_init(self, *a, **k)

    monkeypatch.setattr(StdioServerParameters, "__init__", patched_init)

    captured = {}

    # Patch dspy.ReAct so we never make an LLM call; capture the tools
    # that were merged across both servers.
    import dspy

    class _FakeReAct:
        def __init__(self, signature, tools, max_iters=5):
            captured["tools"] = tools
            captured["signature"] = signature

        async def acall(self, **kwargs):
            class _R:
                process_result = "stub"
            return _R()

    monkeypatch.setattr(dspy, "ReAct", _FakeReAct)

    from plugins.mcp.app.workflows import author as fc

    registry = {
        "caldera_core": {
            "path": str(CORE_SERVER),
            "metadata": {"display_name": "CALDERA Core", "default_enabled": True},
        },
        "range": {
            "path": str(RANGE_SERVER),
            "metadata": {"display_name": "RANGE", "default_enabled": False},
        },
    }

    # Provide a non-empty api_key so the early-exit guard doesn't fire.
    # Yaml model+api_base will win because of the precedence rule we wired in.
    await fc.run(
        adversary_emulation_task="ping",
        lm_obj={"api_key": "stub-not-used", "model": "stub", "max_tool_calls": 3},
        enabled_servers=["caldera_core", "range"],
        server_registry=registry,
    )

    tools = captured["tools"]
    names = [t.name for t in tools]

    core_tools = [n for n in names if n.startswith("core_")]
    range_tools = [n for n in names if n.startswith("range_")]

    assert core_tools, "no core_* tools merged"
    assert range_tools, "no range_* tools merged"
    assert len(set(names)) == len(names), (
        f"tool name collision after merge: {names}"
    )
