"""Tests for cti_taxonomy_loader.py — taxonomy loading and lookup functions."""
import pytest


class TestLoadMitreTaxonomy:
    def test_loads_successfully(self, taxonomy):
        assert "attack_patterns" in taxonomy
        assert "malware" in taxonomy
        assert "tools" in taxonomy
        assert "groups" in taxonomy
        assert "relationships" in taxonomy
        assert "name_index" in taxonomy
        assert "attack_id_index" in taxonomy

    def test_attack_patterns_count(self, taxonomy):
        assert len(taxonomy["attack_patterns"]) >= 800

    def test_relationships_count(self, taxonomy):
        assert len(taxonomy["relationships"]) >= 15000

    def test_caching(self):
        """Second call should return cached result."""
        from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy
        t1 = load_mitre_taxonomy()
        t2 = load_mitre_taxonomy()
        assert t1 is t2  # same object = cached


class TestBuildNormalizedAttackPatterns:
    def test_returns_techniques_and_lookup(self, technique_lookup):
        assert isinstance(technique_lookup, dict)
        assert len(technique_lookup) >= 800

    def test_technique_structure(self, technique_lookup):
        t = technique_lookup.get("T1486")
        assert t is not None
        assert "name" in t
        assert "description" in t
        assert "id" in t
        assert t["id"] == "T1486"

    def test_caching(self):
        """Build should be cached after first call."""
        from plugins.mcp.app.utilities.cti_taxonomy_loader import build_normalized_attack_patterns
        import time
        t0 = time.perf_counter()
        build_normalized_attack_patterns()
        t1 = time.perf_counter()
        build_normalized_attack_patterns()
        t2 = time.perf_counter()
        # Second call should be near-instant
        assert (t2 - t1) < 0.1, "Second call should be cached"


class TestLookupName:
    def test_finds_known_tool(self, taxonomy):
        from plugins.mcp.app.utilities.cti_taxonomy_loader import lookup_name
        result = lookup_name("PsExec", taxonomy)
        assert result is not None

    def test_finds_known_malware(self, taxonomy):
        from plugins.mcp.app.utilities.cti_taxonomy_loader import lookup_name
        result = lookup_name("Cobalt Strike", taxonomy)
        assert result is not None

    def test_returns_none_for_unknown(self, taxonomy):
        from plugins.mcp.app.utilities.cti_taxonomy_loader import lookup_name
        result = lookup_name("NonExistentThing12345", taxonomy)
        assert result is None

    def test_empty_input(self, taxonomy):
        from plugins.mcp.app.utilities.cti_taxonomy_loader import lookup_name
        assert lookup_name("", taxonomy) is None
        assert lookup_name(None, taxonomy) is None


class TestLookupAttackId:
    def test_finds_technique(self, taxonomy):
        from plugins.mcp.app.utilities.cti_taxonomy_loader import lookup_attack_id
        result = lookup_attack_id("T1486", taxonomy)
        assert result is not None
        assert result.get("name")

    def test_subtechnique(self, taxonomy):
        from plugins.mcp.app.utilities.cti_taxonomy_loader import lookup_attack_id
        result = lookup_attack_id("T1003.001", taxonomy)
        assert result is not None

    def test_invalid_id(self, taxonomy):
        from plugins.mcp.app.utilities.cti_taxonomy_loader import lookup_attack_id
        assert lookup_attack_id("T9999", taxonomy) is None
        assert lookup_attack_id("", taxonomy) is None
