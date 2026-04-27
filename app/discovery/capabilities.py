"""Capability discovery.

Mirrors workflow discovery but for Capability registrations. Walks
installed plugins and merges plugin-contributed capabilities with the
MCP plugin's own built-ins into a single registry keyed by capability id.

Built-in capabilities live in plugins/mcp/app/capabilities/*.py and
expose a module-level CAPABILITIES list. External plugins contribute
by dropping a plugins/<name>/mcp/capabilities.py file.
"""

import importlib
import logging
from pathlib import Path

log = logging.getLogger("plugins.mcp")


def _load_capabilities_from_module(module_dotted_path: str, source_path: Path):
    try:
        module = importlib.import_module(module_dotted_path)
    except Exception as e:
        log.warning(
            f"[MCP] Failed to import capabilities from {source_path}: {e}"
        )
        return []
    caps = getattr(module, "CAPABILITIES", None)
    if caps is None:
        return []
    if not isinstance(caps, list):
        log.warning(
            f"[MCP] {source_path} exposes CAPABILITIES but it is not a list"
        )
        return []
    return caps


def discover_capabilities(plugins_root: Path) -> dict:
    """Build a {capability_id: Capability} registry from all installed plugins.

    Sources scanned, in order (later entries shadow earlier ones, so the MCP
    plugin's built-ins win on collision):

      1. plugins/<other_plugin>/mcp/capabilities.py
      2. plugins/mcp/app/capabilities/*.py
    """
    registry: dict = {}

    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name == "mcp":
            continue
        candidate = plugin_dir / "mcp" / "capabilities.py"
        if not candidate.exists():
            continue
        dotted = f"plugins.{plugin_dir.name}.mcp.capabilities"
        for cap in _load_capabilities_from_module(dotted, candidate):
            registry[cap.id] = cap
            log.info(f"[MCP] Discovered capability: {cap.id} from {plugin_dir.name}")

    mcp_caps_dir = plugins_root / "mcp" / "app" / "capabilities"
    if mcp_caps_dir.exists():
        for path in sorted(mcp_caps_dir.glob("*.py")):
            if path.name in {"__init__.py", "base.py"}:
                continue
            dotted = f"plugins.mcp.app.capabilities.{path.stem}"
            for cap in _load_capabilities_from_module(dotted, path):
                registry[cap.id] = cap
                log.info(f"[MCP] Discovered built-in capability: {cap.id}")

    return registry
