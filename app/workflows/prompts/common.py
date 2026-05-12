"""Shared prompt fragments used by MCP workflows."""

from __future__ import annotations

from typing import Any


CHAT_HISTORY_DESC = (
    "Prior turns in this chat session, oldest first. Each turn is "
    "labelled 'User:' / 'Assistant:'. Use them to resolve follow-up "
    "references like 'that profile', 'the instance I just created', "
    "or 'add it to the deployment from earlier'. The current request "
    "still arrives in adversary_emulation_task; chat_history is "
    "context for interpreting it. Empty string on the first turn."
)


CTI_CONTEXT_DESC = (
    "Relevant CTI information supplied by enabled capabilities. This may "
    "include selected STIX bundles, attack patterns, infrastructure, "
    "software, user/account context, identities, and report excerpts. Use "
    "this as grounding, not as permission to invent missing facts."
)


PLAN_EXECUTE_OUTPUT_DESC = (
    "The substantive answer to the user's request. Include the actual data "
    "observed from your tool calls: counts, names, ids, statuses, and any "
    "values the user asked about. When listing things, use a short bulleted "
    "or numbered list with the real names from the observations, not "
    "placeholders. Do NOT narrate which tools you called or describe your "
    "methodology. Do NOT say things like 'I first listed X, then I retrieved "
    "Y'. The user wants the results, not a recap of how you got them. "
    "If a tool failed and you could not retrieve some data, say so clearly "
    "and name what is missing, but still return whatever data you did get."
)


def format_rag_context(rag_context: dict[str, Any] | None) -> str:
    """Format RAG capability output for workflow signatures."""
    if not rag_context:
        return "No CTI context available."

    formatted_parts: list[str] = []
    if "search_results" in rag_context:
        formatted_parts.append("Relevant CTI findings:")
        for i, result in enumerate(rag_context["search_results"][:3], 1):
            formatted_parts.append(f"{i}. {result}")

    if "detailed_context" in rag_context:
        formatted_parts.append("\nDetailed CTI Information:")
        for ctx in rag_context["detailed_context"]:
            formatted_parts.append(f"\n{ctx['name']}:")
            formatted_parts.append(f"{ctx['description']}")

    return "\n".join(formatted_parts)
