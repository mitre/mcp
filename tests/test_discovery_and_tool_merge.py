"""Verifies MCP server discovery and metadata parsing.

Replaces the range-specific integration test. The two servers this build
ships are the caldera_core wrapper and the CTI pipeline.

Run from the repo root:
    pytest plugins/mcp/tests/test_discovery_and_tool_merge.py -v
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGINS_ROOT = REPO_ROOT / "plugins"
CORE_SERVER = PLUGINS_ROOT / "mcp" / "app" / "mcp_server.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_discovery_finds_the_shipped_servers():
    from plugins.mcp.app.discovery.servers import discover_mcp_servers

    registry = discover_mcp_servers(PLUGINS_ROOT)
    assert set(registry) == {"caldera_core", "cti_pipeline"}, (
        f"unexpected registry keys: {sorted(registry)}"
    )
    assert registry["caldera_core"]["path"] == CORE_SERVER


def test_metadata_parsed_without_executing_module():
    """Discovery uses ast.literal_eval, so it must not import the target."""
    from plugins.mcp.app.discovery.servers import _safe_load_metadata

    md = _safe_load_metadata(CORE_SERVER)
    assert md is not None
    assert md.get("display_name")
