"""
Tests for mcp_server.py — MCP server Caldera integration.
Requires Caldera running on localhost:8888.
Tests are skipped if Caldera is not available.
"""
import pytest
import requests

CALDERA_URL = "http://localhost:8888"
API_KEY = "ADMIN123"
HEADERS = {"KEY": API_KEY}


def caldera_available():
    try:
        r = requests.get(f"{CALDERA_URL}/api/v2/health", headers=HEADERS, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


skipif_no_caldera = pytest.mark.skipif(
    not caldera_available(),
    reason="Caldera not running on localhost:8888"
)


@skipif_no_caldera
class TestMCPServerImport:
    """The module must import on its own, and expose the FastMCP app.

    MCPServer and _get_server never existed: git log -S finds no commit that
    added either, so these guarded an API that was never written and could
    only ever fail. What is worth guarding is that the module imports at all,
    which it did not: a bare "from dspy_env import" sat above the sys.path
    insert meant to make it resolvable, so it only worked when sys.path[0]
    happened to be app/.
    """

    def test_the_module_imports_standalone(self):
        from plugins.mcp.app import mcp_server
        assert mcp_server.mcp is not None

    def test_the_imports_below_the_path_insert_resolve(self):
        # Both of these are why the module needs _REPO_ROOT on sys.path.
        from plugins.mcp.app.mcp_server import CreateCommand, caldera_connection
        assert CreateCommand is not None and caldera_connection is not None

    def test_it_registers_tools(self):
        import asyncio
        from plugins.mcp.app.mcp_server import mcp
        tools = asyncio.run(mcp.list_tools())
        assert tools, "the FastMCP app registered no tools"
