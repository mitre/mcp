"""Plan and Execute workflow prompt context."""

from __future__ import annotations

from typing import Any


PLAN_EXECUTE_DESCRIPTION = (
    "Turn CTI into a live adversary-emulation run. Select or upload CTI/STIX, "
    "extract STIX 2.1 entities, infer the victim topology, choose one or more "
    "Range providers, synthesize a deploy spec, provision real infrastructure, "
    "install required services and features, place the starting agent, run "
    "the CALDERA operation, and summarize detection coverage."
)


PLAN_EXECUTE_EXAMPLES = [
    "Create the BlackCat adversary from the selected STIX, build a microvm range from the inferred topology, deploy the starting agent, run it, and summarize detections.",
    "Fuse the selected STIX bundles, infer the victim infrastructure, synthesize a Range deploy spec, and tell me what is ready to deploy.",
    "Convert this raw CTI into STIX 2.1, infer the range topology, and identify any operator-review gaps before deployment.",
    "Plan an emulation against the Discovery adversary on my available agents.",
]


PLAN_EXECUTE_OPERATION_CONTEXT_DESC = (
    "Operator-selected workflow context from the MCP UI: selected STIX "
    "bundle filenames, whether a Range build was requested, preferred "
    "Range provider/hypervisor choices, currently available Range images/features, "
    "and any UI options such as domain/users/agent start preferences. Treat "
    "this as operator intent and live capability context, not CTI evidence."
)


PLAN_EXECUTE_AGENT_DOC = """You are a planner for the CALDERA adversary emulation platform.
You have access to MCP tool servers that wrap CALDERA's core API and any
installed plugins. Your job is to plan and execute operations using existing
abilities, adversaries, CTI pipeline tools, and Range infrastructure tools.

Prefer reusing existing artifacts over creating new ones. Use Range or
infrastructure tools only when the operation requires live targets or the
operator explicitly asks to build a range.

When operation_context contains selected STIX bundles, treat those filenames
as the operator's intended CTI set. If multiple bundles are selected, fuse
them before topology/deploy-spec synthesis. If one bundle is selected, build
or rebuild topology from that bundle. If no bundle is selected, use CTI tools
only when the user's prompt asks for CTI ingest or discovery.

Range execution contract:
- Do not fabricate hosts, users, domains, services, credentials, or network
  edges. Deploy only what the CTI pipeline, Range catalog, tool observations,
  or user supplied context support.
- If the deploy spec marks required infrastructure as missing, return the
  missing items for operator review instead of inventing substitutes.
- Honor the operator-selected Range provider/hypervisor choices from
  operation_context when present.
- Use available Range image and feature context to pick real deployable
  images and feature playbooks. If a required feature does not exist, create
  a custom Ansible feature through the CTI pipeline import-feature tool only
  when the CTI/tool evidence is specific enough to author it safely; otherwise
  report the required feature by name and purpose for operator review.
- When deploying a range, use the CTI pipeline deploy tool, then poll deploy
  status until the range is ready or has failed before waiting for agents or
  starting the operation.
- Install required services/features before agent placement whenever the
  feature pipeline supports it. Agent install should target the CTI-supported
  starting host, not a made-up host.

GROUNDING - non-negotiable: every concrete fact in your output (host names,
user accounts, technique IDs, ability ids, infrastructure types, file paths,
IP addresses, service names, provider names, image names) MUST come from a
tool call result, operation_context, chat_history, or the user's input in this
turn. Do NOT invent or recall such facts from training data. When a tool
returns no data, say so explicitly and name what is missing instead of filling
the gap with plausible-sounding values.

AGNOSTIC TO INPUT - your reasoning must apply equally to any CTI domain:
ransomware, APT campaigns, ICS/OT incidents, supply-chain reports, insider
threats, AI/ML adversaries, or novel TTP write-ups. Let the supplied context
and tools determine what is relevant this turn.

When chat_history is non-empty, treat it as the conversation so far and
interpret the current request in that context. Reuse entity ids that appeared
in earlier turns rather than asking the user to repeat them.

When you produce process_result, return the substantive content the user
asked for (real names, counts, ids, statuses, gaps), not a recap of the tools
you called.
"""


PLAN_EXECUTE_AGENT_WITH_CTI_DOC = """You are a planner for the CALDERA adversary emulation platform,
enhanced with Cyber Threat Intelligence (CTI) data. You have access to MCP
tool servers that wrap CALDERA's core API, the CTI pipeline, Range, and any
installed plugins. Your job is to plan and execute CTI-grounded operations
using existing abilities, adversaries, deploy specs, agents, and Range
infrastructure.

Prefer reusing existing artifacts over creating new ones. Ground your plan in
the provided CTI context so the operation mirrors real-world threat behavior.
Use Range only when the requested workflow needs live infrastructure or when
the operator explicitly selected build_range.

When operation_context contains selected STIX bundles, treat those filenames
as the operator's intended CTI set. If multiple bundles are selected, fuse
them before topology/deploy-spec synthesis. If one bundle is selected, build
or rebuild topology from that bundle. Use the selected Range provider or
providers when present.

Range execution contract:
- Do not fabricate hosts, users, domains, services, credentials, or network
  edges. Deploy only what cti_context, operation_context, tool observations,
  or the user's prompt support.
- If the CTI topology or deploy spec identifies missing required
  infrastructure, return an operator-review gap instead of inventing a host.
- Use Range image/feature capability context to select real images and
  feature playbooks. If a needed feature is absent, create a custom Ansible
  feature through the CTI pipeline import-feature tool only when the CTI/tool
  evidence is specific enough to author it safely; otherwise report the
  required feature by name and purpose for operator review.
- When deploying, call the CTI pipeline deploy tool and poll deploy status
  until ready or failed before waiting for agents or running operations.
- Place the starting agent on the CTI-supported entry host or clearly report
  that the start host is unresolved.

GROUNDING - non-negotiable: every concrete fact you emit (host names, user
accounts, technique IDs, software names, infrastructure types, file paths, IP
addresses, service names, image names) MUST come from cti_context,
operation_context, a tool-call result, chat_history, or the user's input this
turn. Never invent or recall such facts from training data. If cti_context is
silent on something the user asked about, call the appropriate CTI tool first;
if no tool can supply it, say so explicitly. Quote short CTI phrases only when
they are needed to justify a plan decision.

AGNOSTIC TO INPUT - your reasoning must apply equally to any kind of CTI:
ransomware case studies, APT campaign reports, ICS/OT incident write-ups,
insider threat analyses, AI/ML adversary reports, supply-chain breach
narratives, or novel TTP descriptions. Treat each ingested document as the
ground truth for this turn.

When chat_history is non-empty, treat it as the conversation so far and
interpret the current request in that context. Reuse entity ids that appeared
in earlier turns rather than asking the user to repeat them.

When you produce process_result, return the substantive content the user
asked for (real names, counts, ids, statuses, gaps), not a recap of the tools
you called.
"""


def _as_text_list(values: Any, limit: int = 20) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            out.append(value.strip())
        elif isinstance(value, dict):
            name = value.get("name") or value.get("filename") or value.get("profile")
            if name:
                out.append(str(name))
        if len(out) >= limit:
            break
    return out


def _image_summary(images: Any, limit: int = 12) -> list[str]:
    if not isinstance(images, list):
        return []
    out: list[str] = []
    for image in images[:limit]:
        if not isinstance(image, dict):
            continue
        bits = [
            str(image.get("name") or image.get("file") or "unnamed"),
            f"os={image.get('os')}" if image.get("os") else "",
            f"provider={image.get('provider')}" if image.get("provider") else "",
        ]
        out.append(" ".join(bit for bit in bits if bit))
    return out


def format_plan_execute_context(context: dict[str, Any] | None) -> str:
    """Format UI/runtime options as a compact signature input."""
    if not isinstance(context, dict) or not context:
        return ""

    parts: list[str] = []
    selected = _as_text_list(context.get("selected_stix_files"))
    if selected:
        parts.append("Selected STIX bundles:\n" + "\n".join(f"- {x}" for x in selected))

    if "build_range" in context:
        parts.append(f"Build range requested: {bool(context.get('build_range'))}")

    providers = _as_text_list(context.get("range_providers"))
    provider = context.get("range_provider")
    if providers:
        parts.append("Preferred Range providers/hypervisors: " + ", ".join(providers))
    elif provider:
        parts.append(f"Preferred Range provider/hypervisor: {provider}")

    if context.get("cti_uses_rag"):
        parts.append("CTI selection mode: selected STIX bundles are also enabled as RAG context.")

    start = context.get("agent_start")
    if isinstance(start, dict) and start:
        fields = [f"{k}={v}" for k, v in start.items() if v not in (None, "", [])]
        if fields:
            parts.append("Agent start preference: " + ", ".join(fields))

    identity = context.get("identity_options")
    if isinstance(identity, dict) and identity:
        fields = [f"{k}={v}" for k, v in identity.items() if v not in (None, "", [])]
        if fields:
            parts.append("Identity/domain options: " + ", ".join(fields))

    caps = context.get("range_capabilities")
    if isinstance(caps, dict):
        providers = _as_text_list(caps.get("providers"))
        if providers:
            parts.append("Available Range providers: " + ", ".join(providers))

        features = caps.get("features")
        if isinstance(features, dict):
            default = _as_text_list(features.get("default"), limit=30)
            custom = _as_text_list(features.get("custom"), limit=30)
            if default:
                parts.append("Available default Range features: " + ", ".join(default))
            if custom:
                parts.append("Available custom Range features: " + ", ".join(custom))

        images = _image_summary(caps.get("images"))
        image_count = caps.get("image_count")
        if images:
            prefix = f"Available Range images ({image_count} total):" if image_count else "Available Range images:"
            parts.append(prefix + "\n" + "\n".join(f"- {x}" for x in images))

        substrate = caps.get("microvm_substrate")
        if isinstance(substrate, dict) and substrate:
            status = substrate.get("status") or substrate.get("state")
            if status:
                parts.append(f"MicroVM substrate status: {status}")

    return "\n\n".join(parts)
