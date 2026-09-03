"""Workflow contract.

A Workflow is the unit of composition the MCP plugin exposes to the user.
Each workflow ties together:

  - a DSPy signature (the agent persona)
  - a set of MCP servers it requires plus optional ones the user can toggle
  - a list of capability ids it accepts (RAG, future ones)
  - the run() entry point that drives the agent loop
  - a UI component path that renders the workflow's session page

Built-in workflows live under plugins/mcp/app/workflows/. External plugins
contribute additional workflows by dropping a plugins/<name>/mcp/workflows.py
file that exposes WORKFLOWS = [Workflow(...), ...]; discovery picks them up
at boot and merges them into the registry.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import dspy


@dataclass
class Workflow:
    # Stable identifier used in API payloads, MLflow params, and UI routing.
    id: str

    # User-facing label shown on workflow cards.
    display_name: str

    # One or two sentence description for the home-page card.
    description: str

    # The DSPy signature class that defines the agent's persona and IO shape.
    # Fields the workflow accepts from capabilities (e.g. cti_context) must be
    # declared as InputField on this signature with default="" so the workflow
    # still runs when no capability supplies them.
    signature: type[dspy.Signature]

    # MCP server names that must be present for this workflow to be usable.
    # Pinned-on in the UI; if any required server is missing from discovery,
    # the workflow is omitted from /plugin/mcp/workflows entirely.
    required_servers: list[str] = field(default_factory=list)

    # MCP server names the user may toggle on for this workflow. Filtered to
    # what's actually been discovered before being shown.
    optional_servers: list[str] = field(default_factory=list)

    # Capability ids this workflow accepts. The framework only runs a
    # capability's enrich() when its id appears here AND the user enabled it.
    accepted_capabilities: list[str] = field(default_factory=list)

    # Tool names this workflow must never be given, even when the server that
    # exposes them is enabled. Server scoping is all-or-nothing, so a workflow
    # that needs most of a server but must not reach two of its tools has no
    # other way to say so. The agent cannot call a tool that is absent from
    # its list, which is the boundary a persona docstring can only request.
    denied_tools: list[str] = field(default_factory=list)

    # MLflow experiment this workflow's runs belong to. mcp_svc mints the run
    # here, and the boot-time orphan sweep only reconciles runs in the
    # experiments the registered workflows declare.
    mlflow_experiment: str = "caldera-mcp-client-1"

    # Optional plan-then-execute mode. When set, the orchestrator treats the
    # signature's structured output as a plan, hands it to the dotted-path
    # validate function for validation/binding, and executes whatever tool
    # call sequence the validator returns. On validation failure, the error
    # is fed back as the next observation so the agent can retry.
    #
    # Format: "package.module.function". The function must be importable by
    # the framework at request time and must accept a single positional
    # argument (the plan) plus a keyword argument `services` (Caldera's
    # services dict). It returns (ok: bool, error: str, calls: list[dict]).
    plan_validator: str | None = None

    # Path to the Vue component that renders this workflow's session page.
    # Empty string falls back to a generic shell. Paths are relative to the
    # contributing plugin's gui/views/ directory.
    ui_component: str = ""

    # Suggestions surfaced under the prompt input on the session page.
    example_prompts: list[str] = field(default_factory=list)

    # The async entry point. Receives (prompt, lm_obj, **context) where
    # context includes any fields contributed by enabled capabilities plus
    # framework-supplied keys like enabled_servers, server_registry, run_id.
    # Returns a dict with at minimum {"process_result": str}.
    run: Callable[..., Awaitable[dict[str, Any]]] | None = None

    # Whether this workflow benefits from prior-turn context. When True, the
    # orchestrator threads accumulated (prompt, process_result) pairs from the
    # same session into the signature's chat_history input. When False, every
    # turn runs single-shot: the chat UI still renders past turns visually,
    # but the LLM sees a fresh context each time. Author-style workflows where
    # each request is fully self-described should leave this False; workflows
    # that produce entities (abilities, adversaries, operations) referenced by
    # later turns should opt in.
    supports_chat_history: bool = False
