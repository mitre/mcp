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


class TestProvenanceGuards:
    """get_llm_provenance is the third resolver; same invariant applies."""

    @pytest.fixture
    def stub_yaml(self, monkeypatch):
        """The connection lives on llm; a workload profile cannot carry it.
        cti keeps only a generation setting so the guard is still exercised
        through the layered resolution rather than a flat dict."""
        from plugins.mcp.app.utilities import llm_client
        cfg = {
            "llm": {"model": "openai/x", "api_key": "sk-test", "api_base": ""},
            "cti": {"temperature": 0.0},
        }
        monkeypatch.setattr(llm_client, "load_config", lambda: cfg)
        return cfg

    def test_safe_payload_never_carries_credentials(self, stub_yaml):
        from plugins.mcp.app.utilities.llm_client import get_llm_provenance
        base = get_llm_provenance("cti")
        assert "api_key" not in base and "api_base" not in base

    def test_runtime_requires_api_base(self, stub_yaml):
        from plugins.mcp.app.utilities.llm_client import get_llm_provenance
        with pytest.raises(ValueError, match="api_base missing"):
            get_llm_provenance("cti", runtime=True)

    @pytest.mark.parametrize("provider", ["ollama", "azure"])
    def test_runtime_requires_api_base_for_every_provider(self, stub_yaml, provider):
        # This guard used to be gated on openai_compatible, unlike the other two.
        from plugins.mcp.app.utilities.llm_client import get_llm_provenance
        stub_yaml["llm"]["provider"] = provider
        with pytest.raises(ValueError, match="api_base missing"):
            get_llm_provenance("cti", runtime=True)


class TestReadinessPayload:
    """The splash page must not report configured while a run would fail."""

    def _context(self, monkeypatch, api_key, api_base):
        from plugins.mcp.app import mcp_gui
        monkeypatch.setattr(
            mcp_gui, "llm_defaults",
            lambda: {"api_key": api_key, "api_base": api_base, "model": "openai/x"},
        )
        monkeypatch.setattr(mcp_gui, "caldera_connection", dict)
        gui = mcp_gui.McpGUI({}, "mcp", "desc")
        return gui._bootstrap_context()

    def test_configured_needs_both(self, monkeypatch):
        ctx = self._context(monkeypatch, "sk-test", "https://gw/v1")
        assert ctx["llm_configured"] is True
        assert ctx["llm_missing_env"] == []

    def test_api_key_alone_is_not_configured(self, monkeypatch):
        ctx = self._context(monkeypatch, "sk-test", "")
        assert ctx["llm_configured"] is False
        assert ctx["llm_missing_env"] == ["MCP_LLM_API_BASE"]

    def test_names_every_missing_variable(self, monkeypatch):
        ctx = self._context(monkeypatch, "", "")
        assert ctx["llm_missing_env"] == ["MCP_LLM_API_KEY", "MCP_LLM_API_BASE"]

    def test_payload_never_carries_the_key(self, monkeypatch):
        ctx = self._context(monkeypatch, "sk-secret", "https://gw/v1")
        assert "sk-secret" not in str(ctx)


class TestLocalYmlMerge:
    """A partial local.yml must not drop the env wiring from default.yml."""

    def _write(self, tmp_path, name, data):
        import yaml
        conf = tmp_path / "conf"
        conf.mkdir(exist_ok=True)
        (conf / name).write_text(yaml.safe_dump(data))

    @pytest.fixture
    def loader(self, tmp_path, monkeypatch):
        from plugins.mcp.app.utilities import llm_client
        monkeypatch.setattr(llm_client, "get_mcp_root", lambda: tmp_path)
        llm_client.load_config.cache_clear()
        yield llm_client.load_config
        llm_client.load_config.cache_clear()

    def test_local_overlays_rather_than_replaces(self, tmp_path, loader):
        # What the UI's Save writes: no api_key_env, no api_base_env.
        self._write(tmp_path, "default.yml", {
            "llm": {"model": "openai/gpt-oss-120b", "api_key_env": "MCP_LLM_API_KEY"},
            "caldera": {"url_env": "CALDERA_URL"},
        })
        self._write(tmp_path, "local.yml", {"llm": {"model": "devstral"}})
        cfg = loader()
        assert cfg["llm"]["model"] == "devstral"
        assert cfg["llm"]["api_key_env"] == "MCP_LLM_API_KEY"
        assert cfg["caldera"]["url_env"] == "CALDERA_URL"

    def test_unknown_local_sections_do_not_hide_defaults(self, tmp_path, loader):
        # A caller once posted {"config": {...}}, which replaced the whole file.
        self._write(tmp_path, "default.yml", {"llm": {"model": "m"}})
        self._write(tmp_path, "local.yml", {"config": {"cti": {"model": "junk"}}})
        cfg = loader()
        assert cfg["llm"]["model"] == "m"

    def test_default_only_still_loads(self, tmp_path, loader):
        self._write(tmp_path, "default.yml", {"llm": {"model": "m"}})
        assert loader()["llm"]["model"] == "m"

    def test_missing_both_raises(self, tmp_path, loader):
        with pytest.raises(FileNotFoundError):
            loader()


class TestCalderaConnection:
    """Resolution from caldera's own main config. No network: the key check is
    a pure in-process call to caldera's hasher."""

    @pytest.fixture
    def core(self, monkeypatch):
        """Stub caldera's main config; yields it so a test can reshape it."""
        from plugins.mcp.app import config

        main = {"host": "0.0.0.0", "port": 8888}
        monkeypatch.setattr(config, "_caldera_main_config", lambda: main)
        monkeypatch.setattr(
            config, "_load_defaults",
            lambda: {"caldera": {"url_env": "CALDERA_URL",
                                 "api_key_env": "CORE_CALDERA_API_KEY"}},
        )
        monkeypatch.delenv("CALDERA_URL", raising=False)
        monkeypatch.delenv("CORE_CALDERA_API_KEY", raising=False)
        config._key_verdicts.clear()
        yield main
        config._key_verdicts.clear()

    @staticmethod
    def _hash(plaintext):
        from argon2 import PasswordHasher
        return PasswordHasher().hash(plaintext)

    # --- url -------------------------------------------------------------

    def test_wildcard_bind_dials_loopback(self, core):
        # 0.0.0.0 is a wildcard bind, not a routable destination.
        from plugins.mcp.app.config import caldera_connection
        assert caldera_connection()["url"] == "http://127.0.0.1:8888/api/v2/"

    def test_empty_host_dials_loopback(self, core):
        from plugins.mcp.app.config import caldera_connection
        core["host"] = ""
        assert caldera_connection()["url"] == "http://127.0.0.1:8888/api/v2/"

    def test_narrowed_bind_is_used_verbatim(self, core):
        # Binding one NIC leaves loopback unbound, so 127.0.0.1 would refuse.
        from plugins.mcp.app.config import caldera_connection
        core["host"] = "10.0.0.5"
        assert caldera_connection()["url"] == "http://10.0.0.5:8888/api/v2/"

    def test_bare_ipv6_host_is_bracketed(self, core):
        # Unbracketed, requests raises InvalidURL before anything is sent.
        from plugins.mcp.app.config import caldera_connection
        core["host"] = "fe80::1"
        assert caldera_connection()["url"] == "http://[fe80::1]:8888/api/v2/"

    def test_ipv6_wildcard_dials_loopback(self, core):
        from plugins.mcp.app.config import caldera_connection
        core["host"] = "::"
        assert caldera_connection()["url"] == "http://[::1]:8888/api/v2/"

    def test_port_override_is_honoured(self, core):
        from plugins.mcp.app.config import caldera_connection
        core["port"] = 8788
        assert caldera_connection()["url"] == "http://127.0.0.1:8788/api/v2/"

    def test_env_override_wins_and_is_normalised(self, core, monkeypatch):
        # Raw, a suffixless override hits /health instead of /api/v2/health.
        from plugins.mcp.app.config import caldera_connection
        monkeypatch.setenv("CALDERA_URL", "http://caldera.example.com:9000")
        assert caldera_connection()["url"] == "http://caldera.example.com:9000/api/v2/"

    def test_empty_core_config_keeps_the_historical_default(self, monkeypatch):
        from plugins.mcp.app import config
        monkeypatch.setattr(config, "_caldera_main_config", lambda: {})
        monkeypatch.setattr(config, "_load_defaults", lambda: {})
        monkeypatch.delenv("CALDERA_URL", raising=False)
        assert config.caldera_connection()["url"] == "http://127.0.0.1:8888/api/v2/"

    # --- credential ------------------------------------------------------

    def test_stock_key_is_used_when_caldera_accepts_it(self, core):
        # --insecure hashes the shipped ADMIN123 in place, so it still verifies.
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("ADMIN123")
        conn = caldera_connection()
        assert conn["api_key"] == "ADMIN123"
        assert conn["key_valid"] is True

    def test_blue_key_also_counts(self, core):
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("something-else")
        core["api_key_blue"] = self._hash("ADMIN123")
        assert caldera_connection()["key_valid"] is True

    def test_env_key_wins_when_it_verifies(self, core, monkeypatch):
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("generated-token")
        monkeypatch.setenv("CORE_CALDERA_API_KEY", "generated-token")
        conn = caldera_connection()
        assert conn["api_key"] == "generated-token"
        assert conn["key_valid"] is True

    def test_rejected_key_is_still_returned_but_flagged(self, core, monkeypatch):
        # A generated conf/local.yml destroys the plaintext; report, don't swap.
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("generated-token")
        monkeypatch.setenv("CORE_CALDERA_API_KEY", "stale")
        conn = caldera_connection()
        assert conn["api_key"] == "stale"
        assert conn["key_valid"] is False

    def test_stock_key_is_not_flagged_valid_on_a_generated_config(self, core):
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("generated-token")
        conn = caldera_connection()
        assert conn["api_key"] == "ADMIN123"
        assert conn["key_valid"] is False

    def test_explicit_key_is_never_swapped_for_the_stock_one(self, core, monkeypatch):
        # Swapping in ADMIN123 would grant red access the operator never chose.
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("ADMIN123")
        core["api_key_blue"] = self._hash("BLUEADMIN123")
        monkeypatch.setenv("CORE_CALDERA_API_KEY", "BLUEADMIN123x")
        conn = caldera_connection()
        assert conn["api_key"] == "BLUEADMIN123x"
        assert conn["key_valid"] is False

    def test_url_override_skips_verification(self, core, monkeypatch):
        # A cross-host url points at a caldera whose keys we cannot check.
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("ADMIN123")
        monkeypatch.setenv("CALDERA_URL", "http://remote:8888")
        monkeypatch.setenv("CORE_CALDERA_API_KEY", "remote-key")
        conn = caldera_connection()
        assert conn["api_key"] == "remote-key"
        assert conn["key_valid"] is None

    def test_unreadable_core_config_leaves_the_verdict_unknown(self, core):
        # The subprocess shape; must match the pre-fix resolver.
        from plugins.mcp.app.config import caldera_connection
        conn = caldera_connection()
        assert conn["api_key"] == "ADMIN123"
        assert conn["key_valid"] is None

    def test_plaintext_config_rejects_a_mismatched_key(self, core):
        # Caldera <= 5.3.0 stored the key in the clear.
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = "plain-key"
        conn = caldera_connection()
        assert conn["api_key"] == "ADMIN123"
        assert conn["key_valid"] is False

    def test_plaintext_config_accepts_a_matching_env_key(self, core, monkeypatch):
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = "plain-key"
        monkeypatch.setenv("CORE_CALDERA_API_KEY", "plain-key")
        conn = caldera_connection()
        assert conn["api_key"] == "plain-key"
        assert conn["key_valid"] is True

    def test_never_returns_a_password_hash_as_the_credential(self, core):
        # Verification is hash-vs-plaintext, so a hash is never a usable key.
        from plugins.mcp.app.config import caldera_connection
        core["api_key_red"] = self._hash("ADMIN123")
        core["api_key_blue"] = self._hash("BLUEADMIN123")
        assert not caldera_connection()["api_key"].startswith("$argon2id$")

    def test_verdict_is_cached_per_candidate(self, core):
        from plugins.mcp.app import config
        core["api_key_red"] = self._hash("ADMIN123")
        config.caldera_connection()
        assert config._key_verdicts["ADMIN123"] is True


class TestCalderaReadinessPayload:
    """The splash reports a rejected key, and only a genuinely rejected one."""

    def _context(self, monkeypatch, connection):
        from plugins.mcp.app import mcp_gui
        monkeypatch.setattr(
            mcp_gui, "llm_defaults",
            lambda: {"api_key": "sk", "api_base": "https://gw/v1", "model": "m"},
        )
        monkeypatch.setattr(mcp_gui, "caldera_connection", lambda: connection)
        return mcp_gui.McpGUI({}, "mcp", "desc")._bootstrap_context()

    def test_rejected_key_is_flagged(self, monkeypatch):
        ctx = self._context(monkeypatch, {"url": "http://127.0.0.1:8888/api/v2/",
                                          "key_valid": False})
        assert ctx["caldera_key_rejected"] is True

    def test_accepted_key_is_not_flagged(self, monkeypatch):
        ctx = self._context(monkeypatch, {"url": "u", "key_valid": True})
        assert ctx["caldera_key_rejected"] is False

    def test_unknown_verdict_is_not_flagged(self, monkeypatch):
        # A subprocess cannot check, and "unknown" is not a failure to report.
        ctx = self._context(monkeypatch, {"url": "u", "key_valid": None})
        assert ctx["caldera_key_rejected"] is False

    def test_payload_never_carries_the_key(self, monkeypatch):
        ctx = self._context(monkeypatch, {"url": "u", "api_key": "super-secret",
                                          "key_valid": True})
        assert "super-secret" not in str(ctx)


class TestSubprocessEnv:
    """Whatever the parent resolves is what the MCP subprocess must receive."""

    @pytest.fixture(params=["plan_execute", "author"])
    def get_env(self, request, monkeypatch):
        # Both workflows carry the same get_env(); neither may drift.
        mod = pytest.importorskip(f"plugins.mcp.app.workflows.{request.param}")
        monkeypatch.setattr(
            mod, "caldera_connection",
            lambda: {"url": "http://127.0.0.1:8788/api/v2/", "api_key": "resolved-key"},
        )
        return mod.get_env

    def test_pushes_the_resolved_url(self, get_env, monkeypatch):
        # A raw env value skips normalisation and the child only appends to it.
        monkeypatch.setenv("CALDERA_URL", "http://127.0.0.1:8788")
        assert get_env()["CALDERA_URL"] == "http://127.0.0.1:8788/api/v2/"

    def test_pushes_the_resolved_key(self, get_env, monkeypatch):
        monkeypatch.setenv("CORE_CALDERA_API_KEY", "stale")
        assert get_env()["CORE_CALDERA_API_KEY"] == "resolved-key"
