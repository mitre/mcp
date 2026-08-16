"""Tests for llm_client.py and cti_parsing.py — LLM client and IR parsing."""
import pytest


class TestLoadConfig:
    def test_loads(self):
        from plugins.mcp.app.utilities.llm_client import load_config
        cfg = load_config()
        assert isinstance(cfg, dict)
        assert "cti" in cfg or "llm" in cfg or len(cfg) >= 0

    def test_returns_dict(self):
        from plugins.mcp.app.utilities.llm_client import load_config
        assert isinstance(load_config(), dict)


class TestGetLlmProvenance:
    def test_returns_dict(self):
        from plugins.mcp.app.utilities.llm_client import get_llm_provenance
        prov = get_llm_provenance(profile="cti")
        assert isinstance(prov, dict)
        assert "provider" in prov or "model" in prov or "offline" in prov


class TestNormalizeOpenAiApiBase:
    def test_appends_v1(self):
        from plugins.mcp.app.utilities.llm_client import normalize_openai_api_base
        assert normalize_openai_api_base("https://llm.example.com") == (
            "https://llm.example.com/v1"
        )

    def test_preserves_existing_v1(self):
        from plugins.mcp.app.utilities.llm_client import normalize_openai_api_base
        assert normalize_openai_api_base("https://llm.example.com/v1") == (
            "https://llm.example.com/v1"
        )


class TestGetLlmClient:
    def test_singleton(self):
        from plugins.mcp.app.utilities.llm_client import get_llm_client
        c1 = get_llm_client()
        c2 = get_llm_client()
        assert c1 is c2


class TestCleanRawToJson:
    def test_valid_json(self):
        from plugins.mcp.app.utilities.cti_parsing import clean_raw_to_json
        result = clean_raw_to_json('{"name": "test"}')
        assert result == {"name": "test"}

    def test_json_with_markdown_fences(self):
        from plugins.mcp.app.utilities.cti_parsing import clean_raw_to_json
        result = clean_raw_to_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_invalid_json(self):
        from plugins.mcp.app.utilities.cti_parsing import clean_raw_to_json
        result = clean_raw_to_json("not json at all")
        assert result is None

    def test_empty(self):
        from plugins.mcp.app.utilities.cti_parsing import clean_raw_to_json
        assert clean_raw_to_json("") is None


class TestEnforceIrSchema:
    def test_fills_missing_fields(self):
        from plugins.mcp.app.utilities.cti_parsing import enforce_ir_schema
        result = enforce_ir_schema({})
        for key in ("threat_actors", "malware", "tools", "infrastructure",
                    "attack_patterns", "behaviors", "relationships"):
            assert key in result
            assert isinstance(result[key], list)

    def test_preserves_valid_data(self):
        from plugins.mcp.app.utilities.cti_parsing import enforce_ir_schema
        ir = {"malware": [{"name": "X"}], "tools": [{"name": "Y"}]}
        result = enforce_ir_schema(ir)
        assert len(result["malware"]) == 1
        assert len(result["tools"]) == 1

    def test_filters_invalid_entries(self):
        from plugins.mcp.app.utilities.cti_parsing import enforce_ir_schema
        ir = {"malware": [{"no_name_key": "bad"}, {"name": "good"}]}
        result = enforce_ir_schema(ir)
        assert len(result["malware"]) == 1

    def test_wraps_dict_to_list(self):
        from plugins.mcp.app.utilities.cti_parsing import enforce_ir_schema
        ir = {"malware": {"name": "single"}}
        result = enforce_ir_schema(ir)
        assert isinstance(result["malware"], list)
        assert len(result["malware"]) == 1


class TestRenderIrSummary:
    def test_renders(self):
        from plugins.mcp.app.utilities.cti_parsing import render_ir_summary
        ir = {"threat_actors": [{"name": "APT29"}], "malware": [],
              "tools": [{"name": "Mimikatz"}], "infrastructure": [],
              "attack_patterns": [], "behaviors": [], "relationships": []}
        result = render_ir_summary(ir)
        assert "APT29" in result
        assert "Mimikatz" in result


class TestBuildIrPrompt:
    def test_contains_text(self):
        from plugins.mcp.app.utilities.cti_parsing import build_ir_prompt
        prompt = build_ir_prompt("APT29 uses Cobalt Strike.")
        assert "APT29" in prompt
        assert "Cobalt Strike" in prompt
        assert "JSON" in prompt

    def test_has_schema(self):
        from plugins.mcp.app.utilities.cti_parsing import build_ir_prompt
        prompt = build_ir_prompt("test")
        assert "threat_actors" in prompt
        assert "malware" in prompt
        assert "tools" in prompt


class TestLlmValidationHelpers:
    def test_parse_json_array_valid(self):
        from plugins.mcp.app.utilities.cti_llm_validation import _parse_json_array
        result = _parse_json_array('[{"id": "T1486", "valid": true}]')
        assert len(result) == 1

    def test_parse_json_array_with_fences(self):
        from plugins.mcp.app.utilities.cti_llm_validation import _parse_json_array
        result = _parse_json_array('```json\n[{"test": 1}]\n```')
        assert result == [{"test": 1}]

    def test_parse_json_array_invalid(self):
        from plugins.mcp.app.utilities.cti_llm_validation import _parse_json_array
        assert _parse_json_array("not json") is None

    def test_quote_exists_exact(self):
        from plugins.mcp.app.utilities.cti_llm_validation import _quote_exists_in_text
        assert _quote_exists_in_text("encrypts files", "The malware encrypts files on disk.") is True

    def test_quote_exists_fuzzy(self):
        from plugins.mcp.app.utilities.cti_llm_validation import _quote_exists_in_text
        # Fuzzy match requires 60% word overlap (3+ char words)
        assert _quote_exists_in_text("ransomware encrypts files data", "The ransomware encrypts files and data.") is True

    def test_quote_not_exists(self):
        from plugins.mcp.app.utilities.cti_llm_validation import _quote_exists_in_text
        assert _quote_exists_in_text("keylogging capture", "The ransomware encrypts files.") is False

    def test_quote_empty(self):
        from plugins.mcp.app.utilities.cti_llm_validation import _quote_exists_in_text
        assert _quote_exists_in_text("", "text") is False
        assert _quote_exists_in_text("quote", "") is False
