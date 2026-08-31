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
    def test_the_workload_settings_override(self):
        cfg = {"llm": {**GLOBAL, "timeout": 60, "top_p": 1.0},
               "cti": {"timeout": 120, "top_p": 0.9}}
        r = layered_profile(cfg, "cti")
        assert r["timeout"] == 120
        assert r["top_p"] == 0.9

    def test_temperature_and_max_tokens_are_not_overridable(self):
        # Two panels show these, and two stored copies drifted: the CTI panel
        # read 0 and 8192 while the global panel read 0.5 and 24000.
        cfg = {"llm": {**GLOBAL, "temperature": 0.5, "max_tokens": 24000},
               "cti": {"temperature": 0.0, "max_tokens": 4000}}
        r = layered_profile(cfg, "cti")
        assert r["temperature"] == 0.5
        assert r["max_tokens"] == 24000

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

    def test_an_absent_workload_profile_inherits(self):
        # Returning {} here meant a deployment that deleted its cti block got
        # "No LLM profile 'cti'" instead of the connection the UI says it
        # shares with chat.
        r = layered_profile({"llm": GLOBAL}, "cti")
        assert r["model"] == GLOBAL["model"]
        assert r["api_base"] == GLOBAL["api_base"]

    def test_an_empty_workload_profile_inherits(self):
        r = layered_profile({"llm": GLOBAL, "cti": {}}, "cti")
        assert r["model"] == GLOBAL["model"]

    def test_inheriting_does_not_alias_the_global(self):
        cfg = {"llm": dict(GLOBAL)}
        layered_profile(cfg, "cti")["model"] = "mutated"
        assert cfg["llm"]["model"] == GLOBAL["model"]



class TestEmptyValuesFallThrough:
    """A present-but-empty key must not defeat the value it layers over.

    A cleared number input posts '', and a bare `timeout:` parses as None.
    Copied verbatim, timeout=None reaches aiohttp as no timeout at all.
    """

    def test_none_does_not_override(self):
        cfg = {"llm": {**GLOBAL, "timeout": 60}, "cti": {"timeout": None}}
        assert layered_profile(cfg, "cti")["timeout"] == 60

    def test_empty_string_does_not_override(self):
        cfg = {"llm": {**GLOBAL, "max_tokens": 4000}, "cti": {"max_tokens": ""}}
        assert layered_profile(cfg, "cti")["max_tokens"] == 4000

    def test_zero_is_a_real_value_and_still_wins(self):
        cfg = {"llm": {**GLOBAL, "top_p": 0.7}, "cti": {"top_p": 0}}
        assert layered_profile(cfg, "cti")["top_p"] == 0

    def test_false_is_a_real_value_and_still_wins(self):
        cfg = {"llm": {**GLOBAL, "offline": True}, "cti": {"offline": False}}
        assert layered_profile(cfg, "cti")["offline"] is False


class TestWarningIsScopedToRealConflicts:
    def test_a_key_matching_the_global_is_not_reported(self, caplog):
        # The loader promotes a legacy connection onto llm, so the same key is
        # then present on both. Reporting it as ignored contradicts that.
        cfg = {"llm": {**GLOBAL, "model": "devstral"}, "cti": {"model": "devstral"}}
        layered_profile(cfg, "cti")
        assert "ignoring" not in caplog.text

    def test_a_conflicting_key_is_still_reported(self, caplog):
        cfg = {"llm": GLOBAL, "cti": {"model": "devstral"}}
        layered_profile(cfg, "cti")
        assert "ignoring model" in caplog.text
