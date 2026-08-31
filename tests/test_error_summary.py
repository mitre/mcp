"""The failure History shows must be the cause, not the group that wraps it.

An MCP stdio session fails inside nested anyio task groups, so the exception
reaching a handler stringifies as "unhandled errors in a TaskGroup". MLflow
params are immutable, so the first handler to write won and that string is
what the History view displayed instead of the provider error.
"""
import pytest

from plugins.mcp.app.mlflow_run import summarize_exception


CAPACITY = "Qwen/Qwen3-0.6B-Base is temporarily at capacity. Please try again shortly."


def _nested_group(inner):
    # The shape litellm/anyio actually produce: a group inside a group.
    return BaseExceptionGroup(
        "unhandled errors in a TaskGroup",
        [BaseExceptionGroup("unhandled errors in a TaskGroup", [inner])],
    )


def test_the_wrapper_message_is_not_what_gets_recorded():
    grp = _nested_group(RuntimeError(CAPACITY))
    assert str(grp) == "unhandled errors in a TaskGroup (1 sub-exception)"
    assert summarize_exception(grp) == CAPACITY


def test_a_plain_exception_is_unchanged():
    assert summarize_exception(ValueError("boom")) == "boom"


def test_an_empty_message_falls_back_to_the_type():
    assert summarize_exception(_nested_group(TimeoutError())) == "TimeoutError"


class TestSecretsNeverReachTheRunRecord:
    def test_a_key_in_the_message_is_scrubbed(self):
        out = summarize_exception(RuntimeError("key sk-abcdefgh12345678 rejected"))
        assert "sk-abcdefgh12345678" not in out
        assert "sk-***" in out

    def test_it_scrubs_inside_a_group_too(self):
        out = summarize_exception(_nested_group(RuntimeError("bad sk-zzzzzzzz9999")))
        assert "sk-zzzzzzzz9999" not in out


class TestOperatorFacingRewrites:
    @pytest.mark.parametrize("raw,expected", [
        ("failure to get a peer from the ring-balancer", "LLM provider unavailable"),
        ("Incorrect API key provided: sk-xxxxxxxxxxxx", "LLM authentication failed"),
    ])
    def test_known_provider_errors_are_explained(self, raw, expected):
        assert summarize_exception(_nested_group(RuntimeError(raw))).startswith(expected)
