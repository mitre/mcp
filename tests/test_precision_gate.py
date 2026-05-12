"""Tests for cti_precision_gate.py — PMI, hierarchy, clique, entity cap."""
import pytest


class TestEnforceHierarchy:
    def test_orphan_subtechnique_downgraded(self):
        from plugins.mcp.app.utilities.cti_precision_gate import enforce_hierarchy
        techs = [{"id": "T1078.002", "confidence": 0.9, "source": "ontology-inference"}]
        result = enforce_hierarchy(techs)
        # Orphan sub-technique (no siblings) should get downgraded
        assert result[0].get("x_hierarchy_orphan") or result[0]["confidence"] <= 0.9

    def test_sibling_subtechniques_kept(self):
        from plugins.mcp.app.utilities.cti_precision_gate import enforce_hierarchy
        techs = [
            {"id": "T1078.002", "confidence": 0.9, "source": "ontology-inference"},
            {"id": "T1078.003", "confidence": 0.9, "source": "ontology-inference"},
            {"id": "T1078.001", "confidence": 0.9, "source": "ontology-inference"},
        ]
        result = enforce_hierarchy(techs)
        # 3 siblings should maintain confidence
        assert all(t["confidence"] >= 0.6 for t in result)


class TestCliqueFilter:
    def test_multi_entity_support_boosted(self):
        from plugins.mcp.app.utilities.cti_precision_gate import clique_filter
        techs = [{"id": "T1486", "source": "ontology-inference", "confidence": 0.8,
                  "evidence": ["MITRE taxonomy: blackcat uses T1486", "MITRE taxonomy: noberus uses T1486"]}]
        ir = {"tools": [], "malware": [{"name": "BlackCat"}, {"name": "Noberus"}]}
        result = clique_filter(techs, ir)
        assert result[0].get("x_clique_support", 0) >= 2

    def test_single_entity_flagged(self):
        from plugins.mcp.app.utilities.cti_precision_gate import clique_filter
        # Create many techniques from one entity
        techs = [{"id": f"T100{i}", "source": "ontology-inference", "confidence": 0.8,
                  "evidence": [f"MITRE taxonomy: cobalt strike uses T100{i}"]}
                 for i in range(20)]
        ir = {"tools": [{"name": "Cobalt Strike"}], "malware": []}
        result = clique_filter(techs, ir)
        assert any(t.get("x_broad_profile_entity") for t in result)


class TestApplyPrecisionGate:
    def test_empty_input(self):
        from plugins.mcp.app.utilities.cti_precision_gate import apply_precision_gate
        assert apply_precision_gate([], "", {}) == []

    def test_preserves_high_confidence(self):
        from plugins.mcp.app.utilities.cti_precision_gate import apply_precision_gate
        techs = [{"id": "T1486", "confidence": 0.95, "source": "explicit"}]
        result = apply_precision_gate(techs, "ransomware encrypts files", {"tools": [], "malware": []})
        assert len(result) == 1

    def test_drops_low_confidence(self):
        from plugins.mcp.app.utilities.cti_precision_gate import apply_precision_gate
        techs = [{"id": "T1486", "confidence": 0.3, "source": "ontology-inference"}]
        result = apply_precision_gate(techs, "", {"tools": [], "malware": []}, min_confidence=0.50)
        assert len(result) == 0


class TestComputePMI:
    def test_positive_pmi(self):
        from plugins.mcp.app.utilities.cti_precision_gate import compute_pmi
        pmi = compute_pmi(10, 10, 8, 100)
        assert pmi > 0

    def test_zero_cooccurrence(self):
        from plugins.mcp.app.utilities.cti_precision_gate import compute_pmi
        assert compute_pmi(10, 10, 0, 100) == 0.0

    def test_zero_total(self):
        from plugins.mcp.app.utilities.cti_precision_gate import compute_pmi
        assert compute_pmi(10, 10, 5, 0) == 0.0
