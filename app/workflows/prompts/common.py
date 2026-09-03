"""Shared prompt fragments used by MCP workflows."""

from __future__ import annotations



CHAT_HISTORY_DESC = (
    "Prior turns in this chat session, oldest first. Each turn is "
    "labelled 'User:' / 'Assistant:'. Use them to resolve follow-up "
    "references like 'that profile', 'the instance I just created', "
    "or 'add it to the adversary from earlier'. The current request "
    "still arrives in adversary_emulation_task; chat_history is "
    "context for interpreting it. Empty string on the first turn."
)


CTI_CONTEXT_DESC = (
    "The ATT&CK techniques carried by the attached intel, with the report's "
    "own wording where the pipeline captured it, and the named threat actor "
    "when the report identifies one. "
    "Technique-level only: it never contains hosts, accounts, domains, "
    "software or infrastructure. Use this as grounding, not as permission "
    "to invent missing facts."
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


