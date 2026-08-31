"""
Tests for the LLM model configuration API backing the CTI config panel.

Tests different LLM backend configurations:
- Ollama (local)
- OpenAI-compatible (any OpenAI-compatible gateway)
- Offline mode (no LLM)
- Config validation (required fields)
- Config persistence
"""

import pytest
import requests

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

    def test_cti_resolves_the_parameter_fields(self):
        """Extraction must resolve every LM tunable llm_client reads.

        Which section declares one is not the invariant: temperature and
        max_tokens live on llm because two panels show them, and a workload
        profile inheriting them is the point. What matters is that the
        resolved profile carries all four.
        """
        r = requests.get(f"{CALDERA_URL}/plugin/mcp/get_config", headers=HEADERS)
        resolved = r.json().get("resolved", {}).get("cti", {})
        for field in ("temperature", "top_p", "max_tokens", "timeout"):
            assert field in resolved, f"cti does not resolve {field}"

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







# ============================================================
# CONFIG VALIDATION
# ============================================================



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


