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
    # The cause reaches the record; capacity is rewritten to name the model.
    out = summarize_exception(grp)
    assert "TaskGroup" not in out
    assert "Qwen/Qwen3-0.6B-Base" in out


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


class TestProviderErrorsAreExplained:
    """Providers word the same cause three ways and none says where to fix it."""

    @pytest.mark.parametrize("raw", [
        "litellm.NotFoundError: The model `bad/model` does not exist.",
        "Error code: 400 - The model `bad/model` is not available for inference.",
    ])
    def test_an_unavailable_model_names_itself_and_the_setting(self, raw):
        out = summarize_exception(_nested_group(RuntimeError(raw)))
        assert "bad/model" in out
        assert "Global Model Config" in out

    def test_capacity_is_not_confused_with_a_bad_name(self):
        out = summarize_exception(_nested_group(
            RuntimeError("Qwen/Qwen3-0.6B-Base is temporarily at capacity.")))
        assert "busy" in out.lower()
        # The dot in the version must not truncate the name.
        assert "Qwen/Qwen3-0.6B-Base" in out
