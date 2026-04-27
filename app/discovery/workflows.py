"""Workflow discovery.

Walks installed plugins for Workflow registrations and merges them with
the MCP plugin's own built-in workflows into a single registry keyed by
workflow id.

Built-in workflows live in plugins/mcp/app/workflows/*.py and expose a
module-level WORKFLOWS list. External plugins contribute by dropping a
plugins/<name>/mcp/workflows.py file with the same convention.

Unlike server discovery (which uses ast.literal_eval to avoid executing
plugin code), workflow discovery imports the module because Workflow
declarations reference Python classes (signatures) and async functions
that can't be parsed as literals. Plugins that fail to import will be
skipped with a logged warning rather than blocking the rest of the
registry.
"""

import importlib
import importlib.util
import logging
from pathlib import Path

log = logging.getLogger("plugins.mcp")


def _load_workflows_from_module(module_dotted_path: str, source_path: Path):
    """Import a module by dotted path and return its WORKFLOWS list, if any."""
    try:
        module = importlib.import_module(module_dotted_path)
    except Exception as e:
        log.warning(
            f"[MCP] Failed to import workflows from {source_path}: {e}"
        )
        return []
    workflows = getattr(module, "WORKFLOWS", None)
    if workflows is None:
        return []
    if not isinstance(workflows, list):
        log.warning(
            f"[MCP] {source_path} exposes WORKFLOWS but it is not a list"
        )
        return []
    return workflows


def discover_workflows(plugins_root: Path) -> dict:
    """Build a {workflow_id: Workflow} registry from all installed plugins.

    Sources scanned, in order (later entries can shadow earlier ones, so the
    MCP plugin's own workflows take precedence over plugin-contributed ones
    with the same id):

      1. plugins/<other_plugin>/mcp/workflows.py
      2. plugins/mcp/app/workflows/*.py
    """
    registry: dict = {}

    # External plugins first.
    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name == "mcp":
            continue
        candidate = plugin_dir / "mcp" / "workflows.py"
        if not candidate.exists():
            continue
        dotted = f"plugins.{plugin_dir.name}.mcp.workflows"
        for wf in _load_workflows_from_module(dotted, candidate):
            registry[wf.id] = wf
            log.info(f"[MCP] Discovered workflow: {wf.id} from {plugin_dir.name}")

    # MCP plugin's own built-in workflows last so they win on collision.
    mcp_workflows_dir = plugins_root / "mcp" / "app" / "workflows"
    if mcp_workflows_dir.exists():
        for path in sorted(mcp_workflows_dir.glob("*.py")):
            if path.name in {"__init__.py", "base.py"}:
                continue
            dotted = f"plugins.mcp.app.workflows.{path.stem}"
            for wf in _load_workflows_from_module(dotted, path):
                registry[wf.id] = wf
                log.info(f"[MCP] Discovered built-in workflow: {wf.id}")

    return registry
