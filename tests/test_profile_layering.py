"""A workload profile may adjust generation settings, never the connection.

An unrestricted merge let any key under cti win, so a model or api_base
written there sent extraction to a different endpoint from chat with nothing
in the UI to show it.
"""
from plugins.mcp.app.utilities.llm_client import WORKLOAD_OVERRIDABLE, layered_profile


GLOBAL = {
    "provider": "openai_compatible",
    "model": "Qwen/Qwen3-0.6B-Base",
    "api_base": "https://api.featherless.ai/v1",
    "api_key_env": "MCP_LLM_API_KEY",
    "ssl_verify": True,
    "offline": False,
}


class TestConnectionIsNotOverridable:
    def test_model_and_endpoint_come_from_llm(self):
        cfg = {"llm": GLOBAL, "cti": {"model": "devstral",
                                      "api_base": "https://localhost:8443/v1"}}
        r = layered_profile(cfg, "cti")
        assert r["model"] == "Qwen/Qwen3-0.6B-Base"
        assert r["api_base"] == "https://api.featherless.ai/v1"

    def test_tls_and_provider_are_not_overridable(self):
        cfg = {"llm": GLOBAL, "cti": {"ssl_verify": False, "provider": "ollama"}}
        r = layered_profile(cfg, "cti")
        assert r["ssl_verify"] is True
        assert r["provider"] == "openai_compatible"

    def test_unknown_keys_are_dropped(self):
        cfg = {"llm": GLOBAL, "cti": {"extra_headers": {"Host": "x"}}}
        assert "extra_headers" not in layered_profile(cfg, "cti")


class TestGenerationSettingsStillApply:
    def test_temperature_and_tokens_override(self):
        cfg = {"llm": {**GLOBAL, "temperature": 0.5, "max_tokens": 24000},
               "cti": {"temperature": 0.0, "max_tokens": 4000}}
        r = layered_profile(cfg, "cti")
        assert r["temperature"] == 0.0
        assert r["max_tokens"] == 4000

    def test_offline_is_per_workload(self):
        """Extraction can go offline without silencing chat."""
        cfg = {"llm": {**GLOBAL, "offline": False}, "cti": {"offline": True}}
        assert layered_profile(cfg, "cti")["offline"] is True

    def test_every_allowed_key_actually_passes_through(self):
        cfg = {"llm": GLOBAL, "cti": {k: "sentinel" for k in WORKLOAD_OVERRIDABLE}}
        r = layered_profile(cfg, "cti")
        for key in WORKLOAD_OVERRIDABLE:
            assert r[key] == "sentinel", f"{key} is allowed but did not apply"


class TestGlobalProfileIsUntouched:
    def test_llm_returns_itself(self):
        cfg = {"llm": GLOBAL, "cti": {"temperature": 0.0}}
        assert layered_profile(cfg, "llm") == GLOBAL

    def test_absent_workload_profile_is_empty(self):
        assert layered_profile({"llm": GLOBAL}, "cti") == {}
