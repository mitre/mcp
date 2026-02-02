"""
MCP Server (Caldera-native)
==========================

This module exposes Caldera functionality to MCP / FastMCP tools
using *internal Caldera services*, NOT REST API calls.

Key design rules:
- No requests
- No API keys
- No hardcoded URLs
- No /api/v2 usage
- All data access via injected Caldera services

This matches upstream Caldera plugin architecture and is safe for
RBAC, multi-user, and embedded deployments.
"""

from mcp.server.fastmcp import FastMCP
import uuid
from typing import List, Optional

from factory import CreateCommand

# -------------------------------------------------------------------
# MCP bootstrap
# -------------------------------------------------------------------

mcp = FastMCP("Caldera MCP Server")


# -------------------------------------------------------------------
# Service-backed server wrapper
# -------------------------------------------------------------------

class MCPServer:
    """
    Thin wrapper around Caldera internal services.

    This object is instantiated once and reused by MCP tools.
    """

    def __init__(self, services: dict):
        # Core Caldera services
        self.services = services
        self.data_svc = services.get("data_svc")
        self.file_svc = services.get("file_svc")
        self.config_svc = services.get("config_svc")
        self.app_svc = services.get("app_svc")

    # ===============================================================
    # Health / Introspection
    # ===============================================================

    def health(self) -> str:
        """
        Lightweight health check proving Caldera services are reachable.
        """
        _ = self.data_svc
        return "Caldera services are available"

    # ===============================================================
    # Abilities
    # ===============================================================

    def list_abilities(self) -> List[dict]:
        """
        Return all abilities visible to the current user.
        """
        return self.data_svc.locate("abilities", match={})

    def get_ability(self, ability_id: str) -> Optional[dict]:
        """
        Return a single ability by ID.
        """
        results = self.data_svc.locate(
            "abilities",
            match={"ability_id": ability_id},
        )
        return results[0] if results else None

    def get_abilities_by_tactic(self, tactic: str, plugin: str = "stockpile") -> List[dict]:
        """
        Filter abilities by MITRE tactic and plugin (stockpile or atomic).
        """
        abilities = self.list_abilities()
        return [
            {
                "ability_id": a["ability_id"],
                "name": a["name"],
                "tactic": a.get("tactic"),
                "technique": a.get("technique_name"),
            }
            for a in abilities
            if a.get("tactic") == tactic and a.get("plugin") == plugin
        ]

    # ===============================================================
    # Adversaries
    # ===============================================================

    def list_adversaries(self) -> List[dict]:
        """
        Return all adversaries.
        """
        return self.data_svc.locate("adversaries", match={})

    def get_adversary_by_id(self, adversary_id: str) -> Optional[dict]:
        """
        Return a single adversary by ID.
        """
        results = self.data_svc.locate(
            "adversaries",
            match={"adversary_id": adversary_id},
        )
        return results[0] if results else None

    def get_adversary_by_name(self, name: str) -> List[dict]:
        """
        Return adversaries matching a given name.
        """
        return [
            a for a in self.list_adversaries()
            if a.get("name") == name
        ]

    def get_adversaries_by_ability(self, ability_id: str) -> List[dict]:
        """
        Return adversaries that contain a given ability ID.
        """
        adversaries = self.list_adversaries()
        return [
            {
                "adversary_id": a["adversary_id"],
                "name": a["name"],
                "description": a.get("description"),
            }
            for a in adversaries
            if ability_id in (a.get("atomic_ordering") or [])
        ]

    # ===============================================================
    # Agents
    # ===============================================================

    def list_agents(self) -> List[dict]:
        """
        Return all agents (alive, dead, trusted, untrusted).
        """
        return self.data_svc.locate("agents", match={})

    def get_agent(self, paw: str) -> Optional[dict]:
        """
        Return a single agent by paw.
        """
        results = self.data_svc.locate(
            "agents",
            match={"paw": paw},
        )
        return results[0] if results else None

    # ===============================================================
    # Operations
    # ===============================================================

    def list_operations(self) -> List[dict]:
        """
        Return all operations.
        """
        return self.data_svc.locate("operations", match={})

    def get_operation(self, operation_id: str) -> Optional[dict]:
        """
        Return a single operation by ID.
        """
        results = self.data_svc.locate(
            "operations",
            match={"id": operation_id},
        )
        return results[0] if results else None

    # ===============================================================
    # Creation helpers
    # ===============================================================

    def create_adversary(self, name: str, description: str, atomic_ordering: List[str]) -> dict:
        """
        Create and persist a new adversary.
        """
        adversary = {
            "adversary_id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "atomic_ordering": atomic_ordering,
        }
        self.data_svc.store("adversaries", adversary)
        return adversary

    def create_operation(self, operation_name: str, adversary_name: str) -> dict:
        """
        Create a paused operation using an existing adversary.
        """
        adversaries = self.get_adversary_by_name(adversary_name)
        if not adversaries:
            raise ValueError(f"Adversary not found: {adversary_name}")

        adversary = adversaries[0]

        operation = {
            "id": str(uuid.uuid4()),
            "name": operation_name,
            "adversary": adversary,
            "state": "paused",
            "autonomous": True,
            "visibility": 51,
        }
        self.data_svc.store("operations", operation)
        return operation

    # ===============================================================
    # Ability creation
    # ===============================================================

    def create_command(self, description: str, platform: str) -> str:
        """
        Generate a command string using the LLM-backed factory.
        """
        creator = CreateCommand()
        return creator(description=description, platform=platform)

    def create_ability(
            self,
            name: str,
            description: str,
            command_description: str,
            tactic: str,
            technique_name: str,
            platform: str,
            technique_id: Optional[str] = None,
            payloads: Optional[list] = None,
        ) -> dict:
        """
        Create a Linux or Windows ability.
        """
        ability_id = str(uuid.uuid4())
        command = self.create_command(command_description, platform)

        executor = {
            "name": platform,
            "platform": "psh" if platform == "windows" else "sh",
            "command": command,
            "payloads": payloads or [],
            "timeout": 60,
        }

        ability = {
            "ability_id": ability_id,
            "name": name,
            "description": description,
            "tactic": tactic,
            "technique_name": technique_name,
            "technique_id": technique_id,
            "executors": [executor],
            "plugin": "stockpile",
        }

        self.data_svc.store("abilities", ability)
        return ability

    # ===============================================================
    # Payloads
    # ===============================================================

    def list_payloads(self) -> List[dict]:
        """
        Return all payload metadata.
        """
        return self.file_svc.get_payloads()


# -------------------------------------------------------------------
# MCP Tool Bindings
# -------------------------------------------------------------------

_server: MCPServer = None


def _get_server():
    global _server
    if not _server:
        _server = MCPServer(mcp.services)
    return _server


@mcp.tool()
def health_check():
    """Health check"""
    return _get_server().health()


@mcp.tool()
def get_abilities_by_tactic(tactic: str):
    return _get_server().get_abilities_by_tactic(tactic)


@mcp.tool()
def get_ability_by_id(id: str):
    return _get_server().get_ability(id)


@mcp.tool()
def get_adversaries():
    return _get_server().list_adversaries()


@mcp.tool()
def get_adversary_by_id(id: str):
    return _get_server().get_adversary_by_id(id)


@mcp.tool()
def get_adversary_by_name(name: str):
    return _get_server().get_adversary_by_name(name)


@mcp.tool()
def get_all_agents():
    return _get_server().list_agents()


@mcp.tool()
def get_agent_by_paw(paw: str):
    return _get_server().get_agent(paw)


@mcp.tool()
def get_all_operations():
    return _get_server().list_operations()


@mcp.tool()
def get_operation_by_id(id: str):
    return _get_server().get_operation(id)


@mcp.tool()
def create_adversary(name: str, description: str, atomic_ordering: list):
    return _get_server().create_adversary(name, description, atomic_ordering)


@mcp.tool()
def create_operation(operation_name: str, adversary_name: str):
    return _get_server().create_operation(operation_name, adversary_name)


@mcp.tool()
def create_windows_ability(
    name: str,
    description: str,
    command_description: str,
    tactic: str,
    technique_name: str,
    technique_id: str = None,
    payloads: list = None,
):
    return _get_server().create_ability(
        name,
        description,
        command_description,
        tactic,
        technique_name,
        platform="windows",
        technique_id=technique_id,
        payloads=payloads,
    )


@mcp.tool()
def create_linux_ability(
    name: str,
    description: str,
    command_description: str,
    tactic: str,
    technique_name: str,
    technique_id: str = None,
    payloads: list = None,
):
    return _get_server().create_ability(
        name,
        description,
        command_description,
        tactic,
        technique_name,
        platform="linux",
        technique_id=technique_id,
        payloads=payloads,
    )


@mcp.tool()
def get_payloads():
    return _get_server().list_payloads()


if __name__ == "__main__":
    mcp.run()
