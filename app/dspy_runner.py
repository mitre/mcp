"""DSPy ReAct invocation with token-aware error translation.

Both author.py and plan_execute.py drive a `dspy.ReAct(...).acall(...)`
loop. When the LM hits its `max_tokens` budget mid-iteration, DSPy's
ChatAdapter cannot find the closing `[[ ## completed ## ]]` marker and
raises `AdapterParseError`. The raw error is unhelpful: it bubbles up
through nested `AsyncExitStack` / TaskGroup unwinds and the user sees
the chat panel render only "Run failed." with no actionable detail.

This helper centralises the call so both workflows share one error
translation: it preserves the full DSPy stack trace for MLflow / logs
but raises a `WorkflowRunError` whose message points at the real cause
(token budget, model verbosity) and includes the partial LM output so
the operator can spot what the model was doing when it ran out.

Usage:

    from plugins.mcp.app.dspy_runner import safe_react_acall

    result = await safe_react_acall(
        react,
        adversary_emulation_task=prompt,
        cti_context=cti,
    )

The wrapped function still returns the DSPy `Prediction` object
unchanged on success, so workflows do not need any other adjustments.
"""

from __future__ import annotations

import logging
from typing import Any

from dspy.utils.exceptions import AdapterParseError


class WorkflowRunError(RuntimeError):
    """Run-level error with a user-facing message ready for the chat UI.

    `message` is the short, actionable string surfaced into the run
    cache's `error` field. `cause` is the original exception, retained
    for MLflow's traceback log and for chained debugging.
    """

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause


def _truncate(text: str, limit: int = 600) -> str:
    """Trim long LM payloads for inclusion in error messages.

    The chat UI renders these inline; anything past ~600 chars stops
    being useful and starts degrading the failure panel layout.
    """
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def _explain_parse_error(err: AdapterParseError) -> str:
    """Build a human-readable explanation of an AdapterParseError.

    DSPy attaches the offending LM response on the exception. When that
    response stops mid-field, it almost always means the LM hit its
    `max_tokens` budget: the closing `[[ ## completed ## ]]` marker
    never made it into the string. We surface the partial response so
    the user can confirm the model was mid-thought rather than guess
    that it was a real schema mismatch.
    """
    lm_response = getattr(err, "lm_response", "") or ""
    has_completed = "[[ ## completed ## ]]" in lm_response

    if not has_completed:
        head = (
            "LLM response was truncated before DSPy could parse it "
            "(no closing `[[ ## completed ## ]]` marker)."
        )
        cause = (
            "This usually means the model hit its `max_tokens` budget "
            "mid-iteration. Raise `max_tokens` in Global Model "
            "Configuration, or simplify the prompt so each ReAct "
            "iteration produces a shorter thought."
        )
    else:
        head = "LLM response did not match the expected DSPy field shape."
        cause = (
            "The model produced output but the parser could not bind it "
            "to the signature. Inspect the LM response below and adjust "
            "the prompt or signature."
        )

    snippet = _truncate(lm_response)
    if snippet:
        return f"{head} {cause}\n\nLast LM response (truncated):\n{snippet}"
    return f"{head} {cause}"


async def safe_react_acall(
    react,
    *,
    log: logging.Logger | None = None,
    **kwargs: Any,
):
    """Run `react.acall(**kwargs)` and translate parse failures.

    On `AdapterParseError`, raise `WorkflowRunError` with a message
    suitable for surfacing into the run cache's `error` field. All
    other exceptions are re-raised unchanged so existing handlers
    (timeouts, tool errors, network failures) keep their semantics.
    """
    log = log or logging.getLogger("plugins.mcp")
    try:
        return await react.acall(**kwargs)
    except AdapterParseError as e:
        explanation = _explain_parse_error(e)
        log.error(f"[MCP] DSPy parse failure during ReAct: {explanation}")
        raise WorkflowRunError(explanation, cause=e) from e
