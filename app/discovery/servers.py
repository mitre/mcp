import ast
import logging
from pathlib import Path

log = logging.getLogger("plugins.mcp")


def _safe_load_metadata(server_path: Path):
    """Extract a top-level MCP_METADATA literal from an MCP server file.

    Uses ast.literal_eval so plugin code is never executed in the parent
    Caldera process. This also means discovery works even when the
    plugin's runtime dependencies are not installed in the parent env
    (they only need to be available in the subprocess that actually
    runs the server).
    """
    try:
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[MCP] Cannot parse {server_path}: {e}")
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "MCP_METADATA":
                try:
                    return ast.literal_eval(node.value)
                except Exception as e:
                    log.warning(
                        f"[MCP] MCP_METADATA in {server_path} is not a literal: {e}"
                    )
                    return None
    return None


def discover_mcp_servers(plugins_root: Path) -> dict:
    registry = {}

    core_path = plugins_root / "mcp" / "app" / "mcp_server.py"
    registry["caldera_core"] = {
        "path": core_path,
        "metadata": {
            "display_name": "CALDERA Core",
            "default_enabled": True,
            "description": "Wraps Caldera's core v2 REST API",
        },
    }

    # The MCP plugin itself also ships a CTI-pipeline server at the
    # plugin root (plugins/mcp/mcp_server.py). The generic scan below
    # skips plugin_dir == "mcp" because caldera_core already covers the
    # mcp plugin's other server entrypoint, so we register the CTI
    # pipeline server explicitly here. MCP_METADATA on disk wins over
    # the defaults baked in below.
    cti_pipeline_path = plugins_root / "mcp" / "mcp_server.py"
    if cti_pipeline_path.exists():
        # Only reached when the server's own MCP_METADATA could not be read.
        # Restating its description here is how this copy came to advertise a
        # deploy step that no longer exists, so say only what is still true
        # when the metadata is unavailable.
        cti_metadata = _safe_load_metadata(cti_pipeline_path) or {
            "display_name": "CTI Pipeline",
            "default_enabled": False,
            "description": "CTI pipeline tools. Server metadata unavailable.",
        }
        registry["cti_pipeline"] = {
            "path": cti_pipeline_path,
            "metadata": cti_metadata,
        }
        log.info(
            f"[MCP] Discovered MCP server: cti_pipeline -> {cti_pipeline_path}"
        )

    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name == "mcp":
            continue
        candidate = plugin_dir / "mcp_server.py"
        if not candidate.exists():
            continue
        metadata = _safe_load_metadata(candidate)
        if metadata is None:
            log.info(
                f"[MCP] Registering {plugin_dir.name} MCP server "
                f"without MCP_METADATA at {candidate}"
            )
            metadata = {
                "display_name": plugin_dir.name,
                "default_enabled": False,
                "description": "",
            }
        registry[plugin_dir.name] = {"path": candidate, "metadata": metadata}
        log.info(f"[MCP] Discovered MCP server: {plugin_dir.name} -> {candidate}")

    return registry
