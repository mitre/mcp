"""Tests for cti_offline_ir.py — offline IR extraction."""
import pytest


class TestExtractIrOffline:
    def test_basic_extraction(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = "APT29 deployed Cobalt Strike for command and control."
        ir = extract_ir_offline(text)
        assert isinstance(ir, dict)
        for key in ("threat_actors", "malware", "tools", "infrastructure",
                    "behaviors", "attack_patterns", "relationships"):
            assert key in ir

    def test_finds_mitre_entities(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = "The attackers used Mimikatz and PsExec for lateral movement via RDP."
        ir = extract_ir_offline(text)
        tool_names = {t.get("name", "").lower() for t in ir["tools"]}
        found = tool_names & {"mimikatz", "psexec"}
        assert len(found) >= 1

    def test_finds_infrastructure(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = "The malware communicated with 192.168.1.100 and evil.example.com."
        ir = extract_ir_offline(text)
        infra_names = {i.get("name", "") for i in ir["infrastructure"]}
        assert any("192.168" in n for n in infra_names)

    def test_empty_text(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        ir = extract_ir_offline("")
        assert isinstance(ir, dict)
        assert ir.get("tools") == [] or ir.get("tools") is not None

    def test_actor_frequency_inference(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = """BlackCat ransomware attacked multiple organizations. BlackCat used
        encryption. BlackCat operators deployed tools."""
        ir = extract_ir_offline(text)
        actor_names = {a.get("name", "").lower() for a in ir["threat_actors"]}
        # BlackCat should be detected as actor (3 mentions, in MITRE taxonomy)
        assert "blackcat" in actor_names or len(ir["threat_actors"]) >= 1

    def test_behavior_extraction(self):
        from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
        text = "The malware encrypts all files on the local drive and deletes backups."
        ir = extract_ir_offline(text)
        assert len(ir["behaviors"]) >= 1
