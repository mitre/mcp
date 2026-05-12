"""Tests for cti_stix_builders.py — every builder function."""
import pytest
import re


class TestMakeMalware:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_malware
        m = make_malware({"name": "TestMal", "description": "test"})
        assert m["type"] == "malware"
        assert m["spec_version"] == "2.1"
        assert m["name"] == "TestMal"
        assert m["is_family"] is False
        assert m["id"].startswith("malware--")

    def test_empty_name_returns_none(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_malware
        assert make_malware({"name": ""}) is None
        assert make_malware({}) is None

    def test_custom_fields_preserved(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_malware
        m = make_malware({"name": "X", "canonical": "x", "confidence": 0.9})
        assert m["x_canonical"] == "x"
        assert m["x_confidence"] == 0.9


class TestMakeTool:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_tool
        t = make_tool({"name": "Mimikatz"})
        assert t["type"] == "tool"
        assert t["spec_version"] == "2.1"
        assert t["name"] == "Mimikatz"

    def test_with_description(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_tool
        t = make_tool({"name": "X", "description": "cred dump"})
        assert t["description"] == "cred dump"

    def test_none_name(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_tool
        assert make_tool({"name": None}) is None


class TestMakeThreatActor:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_threat_actor
        ta = make_threat_actor({"name": "APT29"})
        assert ta["type"] == "threat-actor"
        assert ta["spec_version"] == "2.1"
        assert "roles" not in ta or ta.get("roles") != ["threat-actor"]

    def test_no_invalid_roles(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_threat_actor
        ta = make_threat_actor({"name": "X"})
        roles = ta.get("roles", [])
        VALID = {"agent", "director", "independent", "infrastructure-architect",
                 "infrastructure-operator", "malware-author", "sponsor"}
        for r in roles:
            assert r in VALID, f"Invalid STIX role: {r}"


class TestMakeInfrastructure:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_infrastructure
        i = make_infrastructure({"name": "C2 Server"})
        assert i["type"] == "infrastructure"
        assert i["spec_version"] == "2.1"


class TestMakeRelationship:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_relationship
        r = make_relationship("uses", "malware--abc", "tool--xyz")
        assert r["type"] == "relationship"
        assert r["spec_version"] == "2.1"
        assert r["relationship_type"] == "uses"
        assert r["source_ref"] == "malware--abc"
        assert r["target_ref"] == "tool--xyz"

    def test_empty_returns_none(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_relationship
        assert make_relationship("", "a", "b") is None
        assert make_relationship("uses", "", "b") is None


class TestMakeAttackPattern:
    def test_with_technique_id(self, taxonomy):
        from plugins.mcp.app.utilities.cti_stix_builders import make_attack_pattern
        ap = make_attack_pattern("T1486", taxonomy)
        assert ap["type"] == "attack-pattern"
        assert ap["spec_version"] == "2.1"
        assert ap["name"]  # should have name from taxonomy
        assert any(r.get("external_id") == "T1486" for r in ap.get("external_references", []))

    def test_with_dict_input(self, taxonomy):
        from plugins.mcp.app.utilities.cti_stix_builders import make_attack_pattern
        ap = make_attack_pattern({"id": "T1490", "confidence": 0.8}, taxonomy)
        assert ap["spec_version"] == "2.1"
        assert ap.get("x_cti_confidence") == 0.8

    def test_unknown_technique_fallback(self, taxonomy):
        from plugins.mcp.app.utilities.cti_stix_builders import make_attack_pattern
        ap = make_attack_pattern("Unknown Technique", taxonomy)
        assert ap["type"] == "attack-pattern"
        assert ap["name"] == "Unknown Technique"


class TestMakeBundle:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_bundle, make_tool
        t = make_tool({"name": "X"})
        b = make_bundle([t])
        assert b["type"] == "bundle"
        assert b["id"].startswith("bundle--")
        assert len(b["objects"]) == 1

    def test_empty_objects(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_bundle
        b = make_bundle([])
        assert b["objects"] == []

    def test_provenance(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_bundle
        b = make_bundle([], model="devstral", provider="openai")
        assert b["x_cti_model"] == "devstral"
        assert b["x_cti_provider"] == "openai"


class TestMakeObservedData:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_observed_data
        od = make_observed_data("suspicious process spawned")
        assert od["type"] == "observed-data"
        assert od["spec_version"] == "2.1"
        assert od["number_observed"] == 1

    def test_empty_returns_none(self):
        from plugins.mcp.app.utilities.cti_stix_builders import make_observed_data
        assert make_observed_data("") is None
        assert make_observed_data(None) is None


class TestNewStixId:
    def test_format(self):
        from plugins.mcp.app.utilities.cti_stix_builders import new_stix_id
        sid = new_stix_id("malware")
        assert sid.startswith("malware--")
        assert len(sid.split("--")[1]) == 36  # UUID4 length

    def test_unique(self):
        from plugins.mcp.app.utilities.cti_stix_builders import new_stix_id
        ids = {new_stix_id("tool") for _ in range(100)}
        assert len(ids) == 100  # all unique
