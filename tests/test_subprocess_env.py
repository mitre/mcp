"""A configured temperature of 0 must reach the subprocess as 0.

conf/default.yml ships temperature 0 because Stage 1 parses the model's own
output as JSON. Both workflows exported it with "or 0.5", and 0.0 is falsy, so
the shipped value was silently replaced by the one it exists to avoid.
"""
import importlib

import pytest

from plugins.mcp.app.dspy_env import ENV_MAX_TOKENS, ENV_TEMPERATURE


@pytest.fixture(params=["author", "plan_execute"])
def get_env(request, monkeypatch):
    # get_env copies os.environ, so a value left there by another run would
    # decide these assertions instead of the settings under test.
    monkeypatch.delenv(ENV_TEMPERATURE, raising=False)
    monkeypatch.delenv(ENV_MAX_TOKENS, raising=False)
    m = importlib.import_module(f"plugins.mcp.app.workflows.{request.param}")
    return m.get_env


BASE = {"model": "m", "api_base": "b"}


class TestZeroTemperatureSurvives:
    def test_zero_is_exported_as_zero(self, get_env):
        assert get_env({**BASE, "temperature": 0.0})[ENV_TEMPERATURE] == "0.0"

    def test_a_real_value_still_passes_through(self, get_env):
        assert get_env({**BASE, "temperature": 0.7})[ENV_TEMPERATURE] == "0.7"

    def test_an_unset_temperature_is_not_exported(self, get_env):
        # Absent means "let the resolver decide", not "force a number here".
        assert ENV_TEMPERATURE not in get_env(dict(BASE))

    def test_max_tokens_behaves_the_same_way(self, get_env):
        assert get_env({**BASE, "max_tokens": 4000})[ENV_MAX_TOKENS] == "4000"


def test_the_fallbacks_match_the_shipped_config():
    # A third resolver disagreeing with conf/default.yml is how the UI and the
    # subprocess ended up on different numbers in the first place.
    from pathlib import Path

    import yaml

    from plugins.mcp.app.dspy_env import _DEFAULTS

    shipped = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "conf" / "default.yml").read_text()
    )["llm"]
    assert _DEFAULTS["temperature"] == shipped["temperature"]
    assert _DEFAULTS["max_tokens"] == shipped["max_tokens"]
