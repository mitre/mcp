"""
Tests for the LLM model configuration API backing the CTI config panel.

Tests different LLM backend configurations:
- Ollama (local)
- OpenAI-compatible (any OpenAI-compatible gateway)
- Offline mode (no LLM)
- Config validation (required fields)
- Config persistence
"""
from pathlib import Path

import pytest
import requests
import json

CALDERA_URL = "http://localhost:8888"
API_KEY = "ADMIN123"
HEADERS = {"KEY": API_KEY}
JSON_HEADERS = {"KEY": API_KEY, "Content-Type": "application/json"}


def mcp_available():
    try:
        r = requests.get(f"{CALDERA_URL}/api/v2/health", headers=HEADERS, timeout=3)
        plugins = r.json().get("plugins", [])
        return any(p.get("name") == "mcp" and p.get("enabled") for p in plugins)
    except Exception:
        return False


skip = pytest.mark.skipif(not mcp_available(), reason="MCP not enabled")

LOCAL_YML = Path(__file__).resolve().parents[1] / "conf" / "local.yml"


@pytest.fixture(autouse=True)
def restore_local_yml():
    """Put conf/local.yml back exactly as it was.

    These tests POST to a live server, which writes the operator's real
    config. An earlier version of this file is how a deployment ended up
    pinned to a gateway nobody had chosen. set_config only merges, so a POST
    cannot undo one: the file itself has to be restored, and the server told
    to reload it.
    """
    before = LOCAL_YML.read_text(encoding="utf-8") if LOCAL_YML.exists() else None
    try:
        yield
    finally:
        if before is None:
            LOCAL_YML.unlink(missing_ok=True)
        else:
            LOCAL_YML.write_text(before, encoding="utf-8")
        # A no-op save is the only route that clears the server's config cache.
        try:
            requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                          headers=JSON_HEADERS, json={"config": {}}, timeout=5)
        except Exception:
            pass


# ============================================================
# CONFIG STRUCTURE TESTS
# ============================================================

@skip
class TestConfigStructure:
    """Test that the cti profile carries the fields the LLM client reads."""

    def test_has_cti_section(self):
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config", headers=HEADERS)
        config = r.json().get("config", r.json())
        assert "cti" in config

    def test_cti_inherits_connection_fields_from_llm(self):
        """cti layers over llm, so provider and model are configured once on
        llm and inherited rather than repeated in both blocks."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config", headers=HEADERS)
        cfg = r.json().get("config", r.json())
        for field in ("provider", "model"):
            assert field in cfg.get("llm", {}), f"llm must define {field}"

        from plugins.mcp.app.utilities.llm_client import layered_profile
        resolved = layered_profile(cfg, "cti")
        for field in ("provider", "model"):
            assert field in resolved, f"cti must resolve {field}"

    def test_cti_has_parameter_fields(self):
        """The cti profile must carry the LM tunables llm_client reads."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config", headers=HEADERS)
        cti = r.json().get("config", r.json()).get("cti", {})
        for field in ("temperature", "top_p", "max_tokens", "timeout"):
            assert field in cti, f"Missing config field: {field}"

    def test_cti_carries_its_own_offline_toggle(self):
        """Offline stays per profile so extraction can be taken offline
        without silencing the planner."""
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config", headers=HEADERS)
        cti = r.json().get("config", r.json()).get("cti", {})
        assert "offline" in cti

    def test_use_mock_is_not_shipped(self):
        """use_mock was a second name for offline with no distinct behaviour.
        Asserted against the shipped defaults rather than the live config,
        which may still carry the key from an operator's local.yml."""
        import yaml
        from plugins.mcp.app.utilities.paths import get_mcp_root
        shipped = yaml.safe_load((get_mcp_root() / "conf" / "default.yml").read_text())
        for profile in ("llm", "cti"):
            assert "use_mock" not in shipped[profile]


# ============================================================
# LLM BACKEND CONFIGURATIONS
# ============================================================

@skip
class TestOllamaConfig:
    """Test Ollama (local) backend configuration."""

    def test_set_ollama_config(self):
        """Set config to use Ollama backend."""
        config = {
            "config": {
                "llm": {
                    "provider": "ollama",
                    "model": "ollama/gemma3n:latest",
                    "api_base": "http://127.0.0.1:11434",
                    "api_key": "ollama",
                },
                "cti": {
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_tokens": 4000,
                    "timeout": 120,
                    "stream": False,
                    "offline": False,
                },
            }
        }
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                         headers=JSON_HEADERS, json=config, timeout=5)
        assert r.status_code == 200


@skip
class TestOpenAICompatibleConfig:
    """Test OpenAI-compatible backend (any OpenAI-compatible gateway)."""

    def test_set_openai_compatible_config(self):
        """Set config to use OpenAI-compatible backend."""
        config = {
            "config": {
                "llm": {
                    "provider": "openai_compatible",
                    "model": "devstral",
                    "api_base": "https://localhost:8443/v1",
                    "api_key": "test-key",
                    "ssl_verify": False,
                },
                "cti": {
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_tokens": 4000,
                    "timeout": 120,
                    "stream": False,
                    "offline": False,
                },
            }
        }
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                         headers=JSON_HEADERS, json=config, timeout=5)
        assert r.status_code == 200

    def test_set_config_with_different_models(self):
        """Test setting different model names."""
        models = ["devstral", "openai/gpt-oss-120b", "nemotron-3-nano",
                  "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"]
        for model in models:
            config = {"config": {"llm": {"model": model, "provider": "openai_compatible"}}}
            r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                             headers=JSON_HEADERS, json=config, timeout=5)
            assert r.status_code == 200, f"Failed to set model: {model}"


@skip
class TestOfflineConfig:
    """Test offline mode configuration."""

    def test_set_offline_mode(self):
        """Enable offline mode (no LLM)."""
        config = {"config": {"cti": {"offline": True}}}
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                         headers=JSON_HEADERS, json=config, timeout=5)
        assert r.status_code == 200

    def test_set_online_mode(self):
        """Disable offline mode."""
        config = {"config": {"cti": {"offline": False}}}
        r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                         headers=JSON_HEADERS, json=config, timeout=5)
        assert r.status_code == 200


# ============================================================
# CONFIG VALIDATION
# ============================================================

@skip
class TestConfigValidation:
    """Test that set_config accepts the value ranges the panel offers."""

    def test_valid_temperature_range(self):
        """Temperature should be 0.0-2.0."""
        for temp in [0.0, 0.5, 1.0, 1.5, 2.0]:
            config = {"config": {"cti": {"temperature": temp}}}
            r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                             headers=JSON_HEADERS, json=config, timeout=5)
            assert r.status_code == 200

    def test_valid_top_p_range(self):
        """top_p should be 0.0-1.0."""
        for tp in [0.0, 0.5, 1.0]:
            config = {"config": {"cti": {"top_p": tp}}}
            r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                             headers=JSON_HEADERS, json=config, timeout=5)
            assert r.status_code == 200

    def test_max_tokens_positive(self):
        """max_tokens should be positive integer."""
        for mt in [256, 1024, 4000, 8192]:
            config = {"config": {"cti": {"max_tokens": mt}}}
            r = requests.post(f"{CALDERA_URL}/plugin/mcp/set_config",
                             headers=JSON_HEADERS, json=config, timeout=5)
            assert r.status_code == 200


# ============================================================
# LLM CLIENT PROVIDER ROUTING
# ============================================================

class TestLlmClientProviders:
    """Test that LLM client routes to correct provider."""

    def test_ollama_provider_recognized(self):
        from plugins.mcp.app.utilities.llm_client import LLMClient
        client = LLMClient()
        # Should not raise on init
        assert client is not None

    def test_config_loading(self):
        from plugins.mcp.app.utilities.llm_client import load_config
        cfg = load_config()
        assert isinstance(cfg, dict)

    def test_provenance_includes_provider(self):
        from plugins.mcp.app.utilities.llm_client import get_llm_provenance
        prov = get_llm_provenance(profile="cti")
        assert "provider" in prov

    def test_provenance_includes_model(self):
        from plugins.mcp.app.utilities.llm_client import get_llm_provenance
        prov = get_llm_provenance(profile="cti")
        assert "model" in prov


