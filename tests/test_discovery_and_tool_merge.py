"""Verifies MCP server discovery and metadata parsing.

Replaces the range-specific integration test. The two servers this build
ships are the caldera_core wrapper and the CTI pipeline.

Run from the repo root:
    pytest plugins/mcp/tests/test_discovery_and_tool_merge.py -v
"""
import sys
from pathlib import Path

import pytest

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


# Backup/snapshot directories under plugins/ often still hold a copy of a real
# plugin's mcp_server.py, which used to register as a phantom duplicate server.
# The filter is driven by name markers only, never by a hardcoded directory.
@pytest.mark.parametrize("name", [
    "pluginx-backup", "backup-pluginx", "pluginx_backup", "pluginx.backup",
    "pluginx-bak", "pluginx.bak",
    "pluginx-backup-2025-01-31",
    "pluginy-old", "pluginy.old",
    "mcp-orig", "mcp.orig", "foo-copy", "foo.copy",
    "bar-snapshot", "bar-snap", "baz-disabled", "baz.disabled",
    "anything-2025-01-31",      # trailing datestamp
    "editorcopy~",              # editor tilde copy
])
def test_backup_like_names_are_filtered(name):
    from plugins.mcp.app.discovery.servers import _looks_like_backup_dir
    assert _looks_like_backup_dir(name) is True


@pytest.mark.parametrize("name", [
    "stockpile", "sandcat", "pluginx", "compass", "pluginy", "mcp",
    "manx", "atomic", "emu", "fieldmanual", "human", "response",
])
def test_real_plugin_names_pass(name):
    from plugins.mcp.app.discovery.servers import _looks_like_backup_dir
    assert _looks_like_backup_dir(name) is False


def test_a_backup_copy_of_a_plugin_server_is_not_registered(tmp_path):
    """End to end through discover_mcp_servers on a throwaway plugins/ tree."""
    from plugins.mcp.app.discovery.servers import discover_mcp_servers

    server = 'MCP_METADATA = {"display_name": "X", "default_enabled": False}\n'
    for name in ("pluginx", "pluginx-backup-2025-01-31"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "mcp_server.py").write_text(server)
    (tmp_path / "mcp" / "app").mkdir(parents=True)

    registry = discover_mcp_servers(tmp_path)
    assert "pluginx" in registry
    assert "pluginx-backup-2025-01-31" not in registry
