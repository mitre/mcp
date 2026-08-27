"""Tests for LLM profile resolution and the api_base guards.

_load_defaults is stubbed throughout, so these read neither
conf/default.yml nor the developer's .env.
"""
import pytest


BASE_YAML = {
    "llm": {
        "model": "openai/gpt-oss-120b",
        "api_base": "",
        "api_base_env": "MCP_LLM_API_BASE",
        "api_key_env": "MCP_LLM_API_KEY",
        "provider": "openai_compatible",
    },
    "cti": {
        "model": "openai/gpt-oss-120b",
        "api_base": "",
        "api_base_env": "MCP_LLM_API_BASE",
        "api_key_env": "MCP_LLM_API_KEY",
        "provider": "openai_compatible",
    },
}


@pytest.fixture
def yaml_defaults(monkeypatch):
    """Stub the yaml loader; yields the dict so a test can reshape it."""
    from plugins.mcp.app import config

    cfg = {key: dict(value) for key, value in BASE_YAML.items()}
    monkeypatch.setattr(config, "_load_defaults", lambda: cfg)
    monkeypatch.delenv("MCP_LLM_API_BASE", raising=False)
    monkeypatch.setenv("MCP_LLM_API_KEY", "sk-test")
    return cfg


class TestResolveEnvIndirection:
    """The one resolver both config.py and the provenance path call."""

    def test_reads_env_var_named_by_api_base_env(self, monkeypatch):
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://gw.example.com")
        resolved = resolve_env_indirection(
            {"api_base": "", "api_base_env": "MCP_LLM_API_BASE"}
        )
        assert resolved["api_base"] == "https://gw.example.com/v1"

    def test_yaml_value_outranks_env(self, monkeypatch):
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://env.example.com")
        resolved = resolve_env_indirection(
            {"api_base": "https://pinned.example.com/v1",
             "api_base_env": "MCP_LLM_API_BASE"}
        )
        assert resolved["api_base"] == "https://pinned.example.com/v1"

    def test_api_key_resolves_env_first(self, monkeypatch):
        # Secrets invert the api_base rule: a yaml literal must not shadow the
        # env var, or rotating .env silently does nothing.
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        monkeypatch.setenv("MCP_LLM_API_KEY", "sk-env")
        resolved = resolve_env_indirection(
            {"api_key": "sk-yaml", "api_key_env": "MCP_LLM_API_KEY"}
        )
        assert resolved["api_key"] == "sk-env"

    def test_api_key_falls_back_to_yaml_when_no_env_var_named(self):
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        assert resolve_env_indirection({"api_key": "sk-yaml"})["api_key"] == "sk-yaml"

    def test_strips_whitespace_from_yaml(self, monkeypatch):
        # Only the env side was covered; an unstripped yaml "   " normalizes
        # to the truthy relative path "/v1" and satisfies every guard.
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        monkeypatch.delenv("MCP_LLM_API_BASE", raising=False)
        resolved = resolve_env_indirection(
            {"api_base": "   ", "api_base_env": "MCP_LLM_API_BASE"}
        )
        assert resolved["api_base"] == ""

    def test_strips_whitespace_from_env(self, monkeypatch):
        # An unstripped blank is truthy and normalizes to the relative "/v1".
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        monkeypatch.setenv("MCP_LLM_API_BASE", "   ")
        resolved = resolve_env_indirection(
            {"api_base": "", "api_base_env": "MCP_LLM_API_BASE"}
        )
        assert resolved["api_base"] == ""

    def test_consumes_env_keys(self, monkeypatch):
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        monkeypatch.setenv("MCP_LLM_API_KEY", "sk-test")
        resolved = resolve_env_indirection(dict(BASE_YAML["llm"]))
        assert "api_base_env" not in resolved
        assert "api_key_env" not in resolved

    def test_does_not_mutate_caller(self, monkeypatch):
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        cfg = dict(BASE_YAML["llm"])
        resolve_env_indirection(cfg)
        assert cfg["api_base_env"] == "MCP_LLM_API_BASE"

    def test_explicit_null_provider_is_coerced(self):
        # setdefault left a yaml `provider:` null in place, silently
        # skipping every `provider == "openai_compatible"` branch.
        from plugins.mcp.app.utilities.llm_client import resolve_env_indirection
        resolved = resolve_env_indirection({"provider": None, "api_base": "https://h"})
        assert resolved["provider"] == "openai_compatible"


class TestProfileDefaults:
    """Both yaml profiles resolve through the same code."""

    def test_unset_env_yields_empty_base(self, yaml_defaults):
        from plugins.mcp.app.config import profile_defaults
        assert profile_defaults("llm")["api_base"] == ""

    def test_llm_and_cti_resolve_identically(self, yaml_defaults, monkeypatch):
        from plugins.mcp.app.config import profile_defaults
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://gw.example.com")
        assert (
            profile_defaults("llm")["api_base"]
            == profile_defaults("cti")["api_base"]
            == "https://gw.example.com/v1"
        )

    def test_cti_may_name_its_own_env_var(self, yaml_defaults, monkeypatch):
        from plugins.mcp.app.config import profile_defaults
        yaml_defaults["cti"]["api_base_env"] = "MCP_CTI_API_BASE"
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://shared.example.com")
        monkeypatch.setenv("MCP_CTI_API_BASE", "https://cti.example.com")
        assert profile_defaults("cti")["api_base"] == "https://cti.example.com/v1"
        assert profile_defaults("llm")["api_base"] == "https://shared.example.com/v1"

    def test_llm_defaults_is_the_llm_profile(self, yaml_defaults):
        from plugins.mcp.app.config import llm_defaults, profile_defaults
        assert llm_defaults() == profile_defaults("llm")


class TestResolveLlmConfig:
    def test_raises_without_api_base(self, yaml_defaults):
        from plugins.mcp.app.config import resolve_llm_config
        with pytest.raises(ValueError, match="No LLM api_base"):
            resolve_llm_config({})

    def test_raises_without_api_key(self, yaml_defaults, monkeypatch):
        from plugins.mcp.app.config import resolve_llm_config
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://gw.example.com")
        monkeypatch.setenv("MCP_LLM_API_KEY", "")
        with pytest.raises(ValueError, match="No LLM API key"):
            resolve_llm_config({})

    @pytest.mark.parametrize("provider", ["ollama", "azure", "wat", None])
    def test_api_base_required_for_every_provider(self, yaml_defaults, provider):
        # The guard used to sit inside `if provider == "openai_compatible"`,
        # so naming any other provider skipped it while model stayed openai/*.
        from plugins.mcp.app.config import resolve_llm_config
        with pytest.raises(ValueError, match="No LLM api_base"):
            resolve_llm_config({"provider": provider})

    def test_ui_override_outranks_env(self, yaml_defaults, monkeypatch):
        from plugins.mcp.app.config import resolve_llm_config
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://env.example.com")
        merged = resolve_llm_config({"api_base": "https://ui.example.com"})
        assert merged["api_base"] == "https://ui.example.com/v1"

    def test_whitespace_override_falls_back_to_default(self, yaml_defaults, monkeypatch):
        # "   " is truthy and normalizes to "/v1", satisfying the guard.
        from plugins.mcp.app.config import resolve_llm_config
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://env.example.com")
        merged = resolve_llm_config({"api_base": "   "})
        assert merged["api_base"] == "https://env.example.com/v1"

    def test_trailing_space_is_trimmed_not_appended(self, yaml_defaults, monkeypatch):
        from plugins.mcp.app.config import resolve_llm_config
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://env.example.com")
        merged = resolve_llm_config({"api_base": "https://ui.example.com/v1 "})
        assert merged["api_base"] == "https://ui.example.com/v1"

    def test_locked_fields_ignore_overrides(self, yaml_defaults, monkeypatch):
        from plugins.mcp.app.config import resolve_llm_config
        yaml_defaults["llm"]["fields_locked"] = {"api_base": True}
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://env.example.com")
        merged = resolve_llm_config({"api_base": "https://ui.example.com"})
        assert merged["api_base"] == "https://env.example.com/v1"

    def test_env_keys_never_reach_the_settings_dict(self, yaml_defaults, monkeypatch):
        from plugins.mcp.app.config import resolve_llm_config
        monkeypatch.setenv("MCP_LLM_API_BASE", "https://gw.example.com")
        merged = resolve_llm_config({})
        assert "api_base_env" not in merged
        assert "api_key_env" not in merged


class TestDspyLmKwargs:
    """The backstop every dspy.LM() in the plugin passes through."""

    def test_builds_kwargs_when_resolved(self):
        from plugins.mcp.app.dspy_env import dspy_lm_kwargs_from_settings
        kwargs = dspy_lm_kwargs_from_settings(
            {"model": "openai/x", "api_key": "k", "api_base": "https://gw/v1"}
        )
        assert kwargs["api_base"] == "https://gw/v1"
        assert kwargs["custom_llm_provider"] == "custom_openai"

    @pytest.mark.parametrize("api_base", ["", "   ", None])
    def test_refuses_to_build_without_api_base(self, api_base):
        # Dropping the falsy base is what let LiteLLM apply its own default.
        from plugins.mcp.app.dspy_env import dspy_lm_kwargs_from_settings
        with pytest.raises(ValueError, match="no api_base"):
            dspy_lm_kwargs_from_settings(
                {"model": "openai/x", "api_key": "k", "api_base": api_base}
            )

    def test_refuses_for_non_openai_providers_too(self):
        from plugins.mcp.app.dspy_env import dspy_lm_kwargs_from_settings
        with pytest.raises(ValueError, match="no api_base"):
            dspy_lm_kwargs_from_settings(
                {"model": "openai/x", "api_key": "k", "provider": "ollama"}
            )
