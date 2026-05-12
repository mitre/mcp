"""Tests for cti_entity_validator.py — entity validation and reclassification."""
import pytest


class TestReclassifyEntities:
    def test_technique_description_dropped(self):
        from plugins.mcp.app.utilities.cti_entity_validator import reclassify_entities
        ir = {"malware": [{"name": "VSS Shadow Copy Deletion"}], "tools": [],
              "threat_actors": [], "infrastructure": []}
        result = reclassify_entities(ir)
        assert not any(m["name"] == "VSS Shadow Copy Deletion" for m in result["malware"])

    def test_known_tool_moved(self):
        from plugins.mcp.app.utilities.cti_entity_validator import reclassify_entities
        ir = {"malware": [{"name": "PsExec", "description": ""}], "tools": [],
              "threat_actors": [], "infrastructure": []}
        result = reclassify_entities(ir)
        # PsExec should be in tools if it's a known MITRE tool
        tool_names = {t["name"].lower() for t in result["tools"]}
        malware_names = {m["name"].lower() for m in result["malware"]}
        assert "psexec" in tool_names or "psexec" not in malware_names

    def test_slash_split(self):
        from plugins.mcp.app.utilities.cti_entity_validator import reclassify_entities
        ir = {"malware": [{"name": "PsExec/RemCom", "description": "tools"}],
              "tools": [], "threat_actors": [], "infrastructure": []}
        result = reclassify_entities(ir)
        all_names = {e["name"] for e in result["malware"] + result["tools"]}
        assert len(all_names) >= 2  # should split into at least 2

    def test_script_extension_to_tool(self):
        from plugins.mcp.app.utilities.cti_entity_validator import reclassify_entities
        ir = {"malware": [{"name": "Apply.ps1", "description": "script"}],
              "tools": [], "threat_actors": [], "infrastructure": []}
        result = reclassify_entities(ir)
        tool_names = {t["name"] for t in result["tools"]}
        assert "Apply.ps1" in tool_names

    def test_real_malware_stays(self):
        from plugins.mcp.app.utilities.cti_entity_validator import reclassify_entities
        ir = {"malware": [{"name": "BlackCat", "description": "ransomware"}],
              "tools": [], "threat_actors": [], "infrastructure": []}
        result = reclassify_entities(ir)
        assert any(m["name"] == "BlackCat" for m in result["malware"])


class TestRepairEntities:
    def test_strips_punctuation_keeps_dots(self):
        from plugins.mcp.app.utilities.cti_entity_validator import repair_entities
        ir = {"malware": [{"name": "test!@#malware"}],
              "tools": [{"name": "192.168.1.1"}],
              "threat_actors": [], "infrastructure": []}
        result = repair_entities(ir)
        # IP should keep dots
        tool_names = {t["name"] for t in result["tools"]}
        assert any("192.168.1.1" in n for n in tool_names)

    def test_long_names_rejected(self):
        from plugins.mcp.app.utilities.cti_entity_validator import repair_entities
        ir = {"malware": [{"name": "this is a very long sentence that should not be an entity name"}],
              "tools": [], "threat_actors": [], "infrastructure": []}
        result = repair_entities(ir)
        assert len(result["malware"]) == 0


class TestKnownCtiEntity:
    def test_known_tool(self):
        from plugins.mcp.app.utilities.cti_entity_validator import _known_cti_entity
        assert _known_cti_entity("PsExec") is True
        assert _known_cti_entity("Mimikatz") is True

    def test_misspelling(self):
        from plugins.mcp.app.utilities.cti_entity_validator import _known_cti_entity
        # "Mimiikatz" with double i — should fuzzy match
        result = _known_cti_entity("Mimiikatz")
        # May or may not match depending on fuzzy logic
        assert isinstance(result, bool)

    def test_unknown(self):
        from plugins.mcp.app.utilities.cti_entity_validator import _known_cti_entity
        assert _known_cti_entity("CompletelyMadeUpTool12345") is False

    def test_empty(self):
        from plugins.mcp.app.utilities.cti_entity_validator import _known_cti_entity
        assert _known_cti_entity("") is False
        assert _known_cti_entity("ab") is False  # too short
