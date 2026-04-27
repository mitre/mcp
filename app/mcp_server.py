import os
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
import requests
from datetime import datetime
import time
import collections
import uuid

from dspy_env import CreateCommand

MCP_METADATA = {
    "display_name": "CALDERA Core",
    "default_enabled": True,
    "description": "Wraps Caldera's core v2 REST API (abilities, adversaries, agents, operations, payloads)",
}

mcp = FastMCP("Caldera Core MCP Server")

class CalderaRequest:
    def __init__(self, url, api_key):
        self.caldera_url = url
        self.api_key = api_key
        self.headers = {"KEY": f"{self.api_key}", "Content-Type": "application/json"}
        self.total_get_requests = collections.defaultdict(list)
        self.total_post_requests = collections.defaultdict(list)

    def make_get_request(self, endpoint):
        response = requests.get(f"{self.caldera_url}{endpoint}", headers=self.headers)
        self.total_get_requests[endpoint].append(
            {
                "time_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "response_code": response.status_code,
            }
        )
        if response.status_code != 200:
            return {"error": f"Request did not return 200. Error: {response.text}"}
        return response.json()

    def make_post_request(self, endpoint, body):
        response = requests.post(
            f"{self.caldera_url}{endpoint}", headers=self.headers, json=body
        )
        self.total_post_requests[endpoint].append(
            {
                "time_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "response_code": response.status_code,
            }
        )
        if response.status_code != 200:
            return {"error": f"Request did not return 200. Error: {response.text}"}
        return response.json()


caldera_request = CalderaRequest(
    url=os.environ.get("CALDERA_URL", "http://localhost:8888/api/v2/"),
    api_key=os.environ.get("CALDERA_API_KEY", "ADMIN123"),
)


@mcp.tool(name="core_health_check")
def health_check():
    """
    Returns the health of the Caldera API.
    """
    if isinstance(caldera_request.make_get_request("health"), dict):
        return "Caldera API is UP!"


def filter_abilities(req, tactic: str, atomic: bool):
    stockpile_abilities = []
    if atomic == True:
        atomic_abilities = [item for item in req if item.get("plugin") == "atomic"]
        tactic_abilities = [
            item for item in atomic_abilities if item.get("tactic") == tactic
        ]
        for ability in tactic_abilities:
            ability_stripped = {}
            ability_stripped["ability_id"] = ability["ability_id"]
            ability_stripped["name"] = ability["name"]
            ability_stripped["tactic"] = ability["tactic"]
            ability_stripped["technique"] = ability["technique_name"]
            stockpile_abilities.append(ability_stripped)
    else:
        stockpile_only = [item for item in req if item.get("plugin") == "stockpile"]
        tactic_abilities = [
            item for item in stockpile_only if item.get("tactic") == tactic
        ]
        for ability in tactic_abilities:
            ability_stripped = {}
            ability_stripped["ability_id"] = ability["ability_id"]
            ability_stripped["name"] = ability["name"]
            ability_stripped["tactic"] = ability["tactic"]
            ability_stripped["technique"] = ability["technique_name"]
            stockpile_abilities.append(ability_stripped)
    return stockpile_abilities or []


@mcp.tool(name="core_get_abilities_by_tactic")
def get_abilities_by_tactic(tactic: str):
    """
    Returns the stockpile abilities of Caldera specified by the tactic.
    Possible Tactic Values:
    - persistence
    - privilege-escalation
    - lateral-movement
    - collection
    - execution
    - command-and-control
    - credential-access
    - discovery
    - defense-evasion
    """
    req = caldera_request.make_get_request("abilities")
    stockpile_abilities = filter_abilities(req, tactic, atomic=False)
    print(f"Stockpile Abilities: {stockpile_abilities}")
    if stockpile_abilities:
        return stockpile_abilities
    else:
        stockpile_abilities = filter_abilities(req, tactic, atomic=True)
        print(f"Stockpile Abilities: {stockpile_abilities}")
        if len(stockpile_abilities) > 5:
            return stockpile_abilities[:5]


@mcp.tool(name="core_get_ability_by_id")
def get_ability_by_id(id: str):
    """
    Returns the ability of the Caldera API specified by the id.
    """
    return caldera_request.make_get_request(f"abilities/{id}")


@mcp.tool(name="core_get_adversaries")
def get_adversaries():
    """
    Returns all Caldera adversaries.
    """
    req = caldera_request.make_get_request("adversaries")
    adversary_list = []
    for adversary in req:
        adversary_stripped = {}
        adversary_stripped["adversary_id"] = adversary["adversary_id"]
        adversary_stripped["name"] = adversary["name"]
        adversary_stripped["description"] = adversary["description"]
        adversary_list.append(adversary_stripped)
    return adversary_list


@mcp.tool(name="core_get_adversary_by_ability_id")
def get_adversary_by_ability_id(ability_id: str, ability_name: str = None):
    """
    Filters all Caldera adversaries by the specifies ability id or ability name.
    """
    req = caldera_request.make_get_request("adversaries")
    adversary_list = []

    abilities = caldera_request.make_get_request("abilities")
    if ability_name:
        named_abilities = [
            item for item in abilities
            if item.get("name") == ability_name
        ]
        ability_id = None
        if named_abilities:
            ability_id = named_abilities[0]["ability_id"]
            for adversary in req:
                for key, value in adversary.items():
                    if key == "atomic_ordering":
                        for atomic_ordering in value:
                            if atomic_ordering == id:
                                adversary_stripped = {}
                                adversary_stripped["adversary_id"] = adversary["adversary_id"]
                                adversary_stripped["name"] = adversary["name"]
                                adversary_stripped["description"] = adversary["description"]
                                adversary_list.append(adversary_stripped)
    elif ability_id:
        for adversary in req:
            for key, value in adversary.items():
                if key == "atomic_ordering":
                    for atomic_ordering in value:
                        if atomic_ordering == ability_id:
                            adversary_stripped = {}
                            adversary_stripped["adversary_id"] = adversary["adversary_id"]
                            adversary_stripped["name"] = adversary["name"]
                            adversary_stripped["description"] = adversary["description"]
                            adversary_list.append(adversary_stripped)
    return adversary_list


@mcp.tool(name="core_get_adversary_by_name")
def get_adversary_by_name(name: str):
    """
    Returns the Caldera adversary specified by the name.
    """
    req = caldera_request.make_get_request("adversaries")
    found_adversaries = []
    for adversary in req:
        if adversary["name"] == name:
            found_adversaries.append(adversary)
    return found_adversaries


@mcp.tool(name="core_get_adversary_by_id")
def get_adversary_by_id(id: str):
    """
    Returns the Caldera adversary specified by the id.
    """
    req = caldera_request.make_get_request(f"adversaries/{id}")
    adversary_stripped = {}
    adversary_stripped["adversary_id"] = req["adversary_id"]
    adversary_stripped["name"] = req["name"]
    adversary_stripped["description"] = req["description"]
    return adversary_stripped


@mcp.tool(name="core_get_all_agents")
def get_all_agents():
    """
    Returns all active and dead agents.
    """

    return caldera_request.make_get_request("agents")


@mcp.tool(name="core_get_agent_by_paw")
def get_agent_by_paw(paw: str):
    """
    Returns the agent of the Caldera API specified by the paw.
    """

    return caldera_request.make_get_request(f"agents/{paw}")


@mcp.tool(name="core_get_all_operations")
def get_all_operations():
    """
    Returns all active and dead operations.
    """

    return caldera_request.make_get_request("operations")


@mcp.tool(name="core_get_operation_by_id")
def get_operation_by_id(id: str):
    """
    Return operation by specified id.
    """

    return caldera_request.make_get_request(f"operations/{id}")


@mcp.tool(name="core_get_operation_links")
def get_operation_links(operation_id: str):
    """
    Specify an operation id to get the links of the operation.
    """

    return caldera_request.make_get_request(f"operations/{operation_id}/links")


@mcp.tool(name="core_get_operation_link")
def get_operation_link(operation_id: str, link_id: str):
    """
    Specify an operation id and link id to get the specific link of the specific operation.
    """

    return caldera_request.make_get_request(
        f"operations/{operation_id}/links/{link_id}"
    )


@mcp.tool(name="core_get_operation_link_result")
def get_operation_link_result(operation_id: str, link_id: str):
    """
    Specify an operation id and link id to get the result of the specific link of the specific operation.
    """

    return caldera_request.make_get_request(
        f"operations/{operation_id}/links/{link_id}/result"
    )


@mcp.tool(name="core_add_link_to_operation")
def add_link_to_operation(
    operation_id: str, ability_id: str, ability_executor: str, paw: str
):
    """
    Add an ability to an existing operation by specifying the operation id, ability id, ability executor, and paw.
    """
    return caldera_request.make_post_request(
        f"operations/{operation_id}/links",
        {"ability_id": ability_id, "ability_executor": ability_executor, "paw": paw},
    )


@mcp.tool(name="core_create_adversary")
def create_adversary(name: str, description: str, atomic_ordering: list):
    """
    Create a new adversary, specify a name, description, and atomic ordering.
    Atomic ordering is a list of ability ids that are used to order the abilities of the adversary.
    Example:
    "665432a4-42e7-4ee1-af19-a9a8c9455d0c",
    "95ad5d69-563e-477b-802b-4855bfb3be09",
    "e99cce5c-cb7e-4a6e-8a09-1609a221b90a",
    "e3db134c-4aed-4c5a-9607-c50183c9ef9e"
    """
    adversary_id = str(uuid.uuid4())

    return caldera_request.make_post_request(
        f"adversaries",
        {
            "adversary_id": adversary_id,
            "name": name,
            "description": description,
            "atomic_ordering": atomic_ordering,
        },
    )


@mcp.tool(name="core_create_operation")
def create_operation(operation_name: str, adversary_name: str):
    """
    Create a new operation with the specified name and adversary.

    Args:
        operation_name: Name for the operation
        adversary_id: ID of the adversary to use for this operation

    Returns:
        The response from the Caldera API or None if adversary details cannot be fetched
    """
    req = caldera_request.make_get_request("adversaries")
    found_adversaries = []
    for adversary in req:
        if adversary["name"] == adversary_name:
            found_adversaries.append(adversary)

    adversary_details = found_adversaries[0]

    operation_body = {
        "name": operation_name,
        "adversary": {
            **{
                k: adversary_details.get(k, "")
                for k in [
                    "adversary_id",
                    "name",
                    "description",
                    "atomic_ordering",
                    "tags",
                    "plugin",
                ]
            },
            "objective": "495a9828-cab1-44dd-a0ca-66e58177d8cc",
        },
        "planner_id": "aaa7c857-37a0-4c4a-85f7-4e9f7f30e31a",
        "source_id": "ed32b9c3-9593-4c33-b0db-e2007315096b",
        "objective_id": "495a9828-cab1-44dd-a0ca-66e58177d8cc",
        "state": "paused",
        "autonomous": 1,
        "auto_close": False,
        "obfuscator": "plain-text",
        "jitter": "2/4",
        "visibility": 51,
        "use_learning_parsers": True,
        "group": "",
    }

    return caldera_request.make_post_request("operations", operation_body)


def create_command(description: str, platform: str):
    """
    create a command by specifying a description of the command(what it does and how it works) and the platform it is for (windows or linux).
    """

    create_command = CreateCommand()
    return create_command(description=description, platform=platform)


@mcp.tool(name="core_create_windows_ability")
def create_windows_ability(
    name: str,
    description: str,
    command_description: str,
    tactic: str,
    technique_name: str,
    technique_id: str = None,
    payloads: list = None,
):
    """
    Create a new windows ability with the specified parameters.

    Args:
        name: Name of the ability
        description: Description of what the ability does
        command_description: Detailed description of the command to use in the windows ability
        tactic: MITRE ATT&CK tactic (e.g., 'privilege-escalation', 'discovery')
        technique_name: Name of the MITRE ATT&CK technique
        technique_id: Optional MITRE ATT&CK technique ID (e.g., 'T1548.002')
        payloads: Optional list of payload files needed

    Returns:
        The response from the Caldera API
    """
    ability_id = str(uuid.uuid4())
    created_command = create_command(command_description, "windows")
    # Create the executor object with default values for optional fields
    executor = {
        "name": "windows",
        "platform": "psh",
        "command": created_command,
        "code": None,
        "language": None,
        "build_target": None,
        "payloads": payloads or [],
        "uploads": [],
        "timeout": 60,
        "parsers": [],
        "cleanup": [],
        "variations": [],
        "additional_info": {},
    }

    ability_body = {
        "ability_id": ability_id,
        "tactic": tactic,
        "technique_name": technique_name,
        "technique_id": technique_id,
        "name": name,
        "description": description,
        "executors": [executor],
        "requirements": [],
        "privilege": "",
        "repeatable": False,
        "buckets": [tactic],
        "additional_info": {},
        "access": {},
        "singleton": False,
        "plugin": "stockpile",
        "delete_payload": True,
    }

    return caldera_request.make_post_request("abilities", ability_body)


@mcp.tool(name="core_create_linux_ability")
def create_linux_ability(
    name: str,
    description: str,
    command_description: str,
    tactic: str,
    technique_name: str,
    technique_id: str = None,
    payloads: list = None,
):
    """
    Create a new linux ability with the specified parameters.

    Args:
        name: Name of the ability
        description: Description of what the ability does
        command_description: Detailed description of the command to use in the linux ability
        tactic: MITRE ATT&CK tactic (e.g., 'privilege-escalation', 'discovery')
        technique_name: Name of the MITRE ATT&CK technique
        technique_id: Optional MITRE ATT&CK technique ID (e.g., 'T1548.002')
        payloads: Optional list of payload files needed

    Returns:
        The response from the Caldera API
    """
    ability_id = str(uuid.uuid4())
    created_command = create_command(command_description, "linux")

    # Create the executor object with default values for optional fields
    executor = {
        "name": "linux",
        "platform": "sh",
        "command": created_command,
        "code": None,
        "language": None,
        "build_target": None,
        "payloads": payloads or [],
        "uploads": [],
        "timeout": 60,
        "parsers": [],
        "cleanup": [],
        "variations": [],
        "additional_info": {},
    }

    ability_body = {
        "ability_id": ability_id,
        "tactic": tactic,
        "technique_name": technique_name,
        "technique_id": technique_id,
        "name": name,
        "description": description,
        "executors": [executor],
        "requirements": [],
        "privilege": "",
        "repeatable": False,
        "buckets": [tactic],
        "additional_info": {},
        "access": {},
        "singleton": False,
        "plugin": "stockpile",
        "delete_payload": True,
    }

    return caldera_request.make_post_request("abilities", ability_body)


@mcp.tool(name="core_get_payloads")
def get_payloads():
    """
    Returns all payloads.
    """
    return caldera_request.make_get_request("payloads")


if __name__ == "__main__":
    mcp.run()