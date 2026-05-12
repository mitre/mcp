"""Tests for cti_mitre_extract.py — MITRE technique extraction."""
import pytest


class TestExtractIdsFromText:
    def test_finds_technique_ids(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text
        text = "The actor used T1486 and T1490 for impact."
        ids = extract_ids_from_text(text, {"T1486": {}, "T1490": {}})
        assert "T1486" in ids
        assert "T1490" in ids

    def test_finds_subtechniques(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text
        text = "Credential dumping via T1003.001 was observed."
        ids = extract_ids_from_text(text, {"T1003.001": {}})
        assert "T1003.001" in ids

    def test_no_false_positives(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text
        text = "No techniques here, just normal text about security."
        ids = extract_ids_from_text(text, {})
        assert len(ids) == 0

    def test_empty_text(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text
        assert extract_ids_from_text("", {}) == []
        assert extract_ids_from_text(None, {}) == []

    def test_only_valid_ids(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text
        text = "T1486 is real, T9999 is not in lookup."
        ids = extract_ids_from_text(text, {"T1486": {}})
        assert "T1486" in ids
        assert "T9999" not in ids


class TestTechniqueScore:
    def test_behavior_anchoring(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import technique_score
        tech = {"tokens": {"encrypt", "file", "impact"}}
        behavior_tokens = {"encrypt", "file"}
        doc_tokens = {"ransomware", "encrypt", "file", "victim"}
        score = technique_score(tech, behavior_tokens, doc_tokens)
        assert score > 0

    def test_no_overlap(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import technique_score
        tech = {"tokens": {"keylog", "capture"}}
        behavior_tokens = {"encrypt", "file"}
        doc_tokens = set()
        score = technique_score(tech, behavior_tokens, doc_tokens)
        assert score == 0  # no token overlap, no score


class TestConvertSets:
    def test_converts_sets_to_lists(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import convert_sets
        data = {"tokens": {"a", "b", "c"}, "name": "test"}
        result = convert_sets(data)
        assert isinstance(result["tokens"], list)
        assert result["name"] == "test"

    def test_nested(self):
        from plugins.mcp.app.utilities.cti_mitre_extract import convert_sets
        data = {"outer": [{"inner": {"x", "y"}}]}
        result = convert_sets(data)
        assert isinstance(result["outer"][0]["inner"], list)
