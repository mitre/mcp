"""Tests for cti_stix_builders.py — every builder function."""




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
        from plugins.mcp.app.utilities.cti_stix_builders import make_bundle, make_threat_actor
        t = make_threat_actor({"name": "X"})
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
