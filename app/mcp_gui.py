"""Server-rendered HTML pages for the MCP plugin.

The plugin's main interactive UI is a Vue SPA bundled by magma; those
components live in plugins/mcp/gui/views/. This class only owns the
small set of jinja2-rendered pages Caldera serves directly:

  splash() — the plugin's landing page. Reports readiness (LLM key,
             discovered registries, Caldera REST connection) so a user
             opening the plugin sees up-front whether everything is
             wired correctly before stepping into the workspace.
"""
from aiohttp_jinja2 import template

from app.service.auth_svc import for_all_public_methods, check_authorization
from app.utility.base_world import BaseWorld

from plugins.mcp.app.config import llm_defaults, caldera_connection


@for_all_public_methods(check_authorization)
class McpGUI(BaseWorld):

    def __init__(self, services, name, description):
        self.name = name
        self.description = description
        self.services = services
        self.auth_svc = services.get("auth_svc")

    @template("mcp.html")
    async def splash(self, request):
        """Render the plugin landing / readiness page."""
        return self._bootstrap_context()

    def _bootstrap_context(self) -> dict:
        """Collect the plugin-readiness snapshot the splash template renders.

        Each probe degrades gracefully so a partially broken plugin still
        renders a useful diagnostic page instead of a 500. The template
        decides what to show; this method just gathers state.
        """
        mcp_svc = self.services.get("mcp_svc")

        try:
            llm = llm_defaults()
        except Exception:
            llm = {}

        try:
            caldera = caldera_connection()
        except Exception:
            caldera = {}

        servers = getattr(mcp_svc, "server_registry", None) or {}
        workflows = getattr(mcp_svc, "workflow_registry", None) or {}
        capabilities = getattr(mcp_svc, "capability_registry", None) or {}

        return {
            "name": self.name,
            "description": self.description,
            "llm_configured": bool(llm.get("api_key")),
            "llm_model": llm.get("model") or "",
            "llm_api_base": llm.get("api_base") or "",
            "llm_api_key_env": "MCP_LLM_API_KEY",
            "caldera_url": caldera.get("url") or "",
            "caldera_api_key_env": caldera.get("api_key_env") or "CORE_CALDERA_API_KEY",
            "server_names": sorted(servers.keys()),
            "workflow_names": sorted(workflows.keys()),
            "capability_names": sorted(capabilities.keys()),
            "server_count": len(servers),
            "workflow_count": len(workflows),
            "capability_count": len(capabilities),
        }
