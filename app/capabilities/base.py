"""Capability contract.

A Capability is an orthogonal modifier that enriches a workflow's prompt
context. Capabilities run before the workflow's main agent loop and
contribute extra fields that are merged into the workflow signature's
input fields by name.

The canonical capability is RAG (CTI ingestion): it embeds uploaded
bundles, retrieves relevant chunks for the user's prompt, and contributes
a cti_context string to whatever workflow accepts it.

Workflows opt into capabilities via Workflow.accepted_capabilities.
Capability output reaches a workflow only when:
  - the workflow's accepted_capabilities list includes the capability's id
  - the user has enabled the capability for this run
  - the workflow's signature has an InputField with a name matching one
    of the capability's contributes_fields entries

Built-in capabilities live under plugins/mcp/app/capabilities/. External
plugins contribute additional capabilities by dropping a
plugins/<name>/mcp/capabilities.py file that exposes
CAPABILITIES = [Capability(...), ...]; discovery picks them up at boot.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class Capability:
    # Stable identifier used in API payloads and workflow accepted_capabilities.
    id: str

    # User-facing label for the capability's settings panel.
    display_name: str

    # One or two sentence description shown in the panel header.
    description: str

    # Async function that runs before the workflow's agent loop.
    # Receives (prompt, settings) where settings is the per-capability dict
    # the user supplied (e.g. {"rag_files": [...], "topk": 5}).
    # Returns a dict whose keys match the workflow signature's input fields
    # the capability is contributing to.
    enrich: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None

    # Path to the Vue component that renders this capability's settings.
    # Empty string means the capability has no user-tunable settings.
    # Paths are relative to the contributing plugin's gui/views/ directory.
    ui_settings_component: str = ""

    # Names of signature input fields this capability contributes. Used by
    # the framework to warn at registration time when a workflow accepts
    # this capability but its signature has no matching input field.
    contributes_fields: list[str] = field(default_factory=list)
