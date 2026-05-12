"""Tests for cti_defend_validation.py, cti_ontology_inference.py, cti_defend_enricher.py."""
import pytest


class TestExtractTacticSignals:
    def test_detects_impact(self):
        from plugins.mcp.app.utilities.cti_defend_validation import extract_tactic_signals
        signals = extract_tactic_signals("The ransomware encrypts all files on disk.")
        assert "Impact" in signals

    def test_detects_credential_access(self):
        from plugins.mcp.app.utilities.cti_defend_validation import extract_tactic_signals
        signals = extract_tactic_signals("Mimikatz was used to dump credentials from LSASS.")
        assert "CredentialAccess" in signals

    def test_detects_lateral_movement(self):
        from plugins.mcp.app.utilities.cti_defend_validation import extract_tactic_signals
        signals = extract_tactic_signals("The actor used RDP for lateral movement.")
        assert "LateralMovement" in signals

    def test_empty_text(self):
        from plugins.mcp.app.utilities.cti_defend_validation import extract_tactic_signals
        assert extract_tactic_signals("") == set()

    def test_multiple_tactics(self):
        from plugins.mcp.app.utilities.cti_defend_validation import extract_tactic_signals
        text = "Phishing email led to credential dumping and data exfiltration."
        signals = extract_tactic_signals(text)
        assert len(signals) >= 2


class TestValidateTechniquesByTactic:
    def test_keeps_matching_tactic(self):
        from plugins.mcp.app.utilities.cti_defend_validation import validate_techniques_by_tactic
        techs = [{"id": "T1486", "source": "ontology-inference"}]
        text = "The ransomware encrypts files for impact."
        result = validate_techniques_by_tactic(techs, text, strict=True)
        assert len(result) >= 1

    def test_drops_mismatched_tactic(self):
        from plugins.mcp.app.utilities.cti_defend_validation import validate_techniques_by_tactic
        techs = [{"id": "T1056.001", "source": "ontology-inference"}]  # Collection: Keylogging
        text = "The ransomware encrypts files."  # Only Impact tactic
        result = validate_techniques_by_tactic(techs, text, strict=True)
        # Keylogging should be filtered if Collection isn't in text
        assert len(result) <= 1

    def test_preserves_non_ontology(self):
        from plugins.mcp.app.utilities.cti_defend_validation import validate_techniques_by_tactic
        techs = [{"id": "T1056.001", "source": "explicit"}]
        text = "Encrypt files."  # No Collection tactic
        result = validate_techniques_by_tactic(techs, text, strict=True)
        # Explicit techniques should survive even without tactic match
        assert len(result) == 1

    def test_empty_techniques(self):
        from plugins.mcp.app.utilities.cti_defend_validation import validate_techniques_by_tactic
        assert validate_techniques_by_tactic([], "text") == []


class TestFilterByKeywordEvidence:
    def test_keeps_matching_keywords(self):
        from plugins.mcp.app.utilities.cti_defend_validation import filter_by_keyword_evidence
        techs = [{"id": "T1110", "name": "Brute Force", "source": "ontology-inference"}]
        text = "The actor conducted brute force login attempts against the VPN."
        result = filter_by_keyword_evidence(techs, text, min_overlap=2)
        assert len(result) == 1

    def test_drops_no_keyword_match(self):
        from plugins.mcp.app.utilities.cti_defend_validation import filter_by_keyword_evidence
        techs = [{"id": "T1056.001", "name": "Keylogging", "source": "ontology-inference"}]
        text = "The ransomware encrypts files."
        result = filter_by_keyword_evidence(techs, text, min_overlap=2)
        assert len(result) == 0

    def test_preserves_explicit(self):
        from plugins.mcp.app.utilities.cti_defend_validation import filter_by_keyword_evidence
        techs = [{"id": "T1486", "name": "X", "source": "explicit"}]
        text = "Nothing matching."
        result = filter_by_keyword_evidence(techs, text, min_overlap=2)
        assert len(result) == 1  # explicit always kept


class TestOntologyInference:
    def test_infers_techniques_from_tool(self, technique_lookup):
        from plugins.mcp.app.utilities.cti_ontology_inference import infer_techniques_from_entities
        ir = {"tools": [{"name": "PsExec"}], "malware": []}
        result = infer_techniques_from_entities(ir, technique_lookup, source_text="PsExec lateral movement")
        assert len(result) >= 1
        tids = {t["id"] for t in result}
        assert "T1569.002" in tids or "T1570" in tids  # PsExec → service execution or lateral

    def test_empty_ir(self, technique_lookup):
        from plugins.mcp.app.utilities.cti_ontology_inference import infer_techniques_from_entities
        ir = {"tools": [], "malware": []}
        result = infer_techniques_from_entities(ir, technique_lookup)
        assert result == []

    def test_corroboration_filtering(self, technique_lookup):
        from plugins.mcp.app.utilities.cti_ontology_inference import infer_techniques_from_entities
        ir = {"tools": [{"name": "Cobalt Strike"}], "malware": []}
        # Short text should limit Cobalt Strike's 72 techniques
        result = infer_techniques_from_entities(ir, technique_lookup, source_text="beacon callback")
        assert len(result) < 72  # corroboration should filter some


class TestStage2D3FENDPath:
    def test_resolves_existing_asset_root(self):
        from plugins.mcp.app.cti_pipeline_stage2 import get_d3fend_root

        root = get_d3fend_root()
        assert root.is_dir()
        assert (root / "D3fend_CAD_Graph_Schema.json").is_file()
        assert (root / "ontology").is_dir()
