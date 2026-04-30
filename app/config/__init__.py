"""Configuration for the MCP plugin: parent and subprocess halves.

  parent     resolves yaml + .env + UI overrides for the parent process.
             Used by mcp_svc, mcp_api, the workflow modules, and mcp_gui.

  subprocess bootstraps DSPy in spawned MCP server subprocesses from the
             env vars the parent forwards. Used only by code that runs
             inside a spawned mcp_server.py.

The two halves do not share imports (the subprocess does not have
Caldera's framework on sys.path), but they share the env-var contract
documented in subprocess.py and consumed in lockstep with parent.py.

The package re-exports the parent-side public API so existing imports
keep working unchanged:

    from plugins.mcp.app.config import resolve_llm_config

Subprocess-context code imports the bootstrap from its submodule:

    from config.subprocess import ensure_lm_configured
"""
from .parent import (
    llm_defaults,
    caldera_connection,
    resolve_llm_config,
)

__all__ = ["llm_defaults", "caldera_connection", "resolve_llm_config"]
