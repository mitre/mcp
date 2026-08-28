"""Multi-bundle STIX fusion."""


def test_fuse_bundles_merges_by_mitre_id_and_remaps_relationships():
    from plugins.mcp.app.utilities.cti_fusion import fuse_bundles

    ap1 = {
        "type": "attack-pattern",
        "id": "attack-pattern--00000000-0000-4000-8000-000000000001",
        "name": "Technique A",
        "external_references": [
            {"source_name": "mitre-attack", "external_id": "T1234"}
        ],
    }
    ap2 = {
        "type": "attack-pattern",
        "id": "attack-pattern--00000000-0000-4000-8000-000000000002",
        "name": "Technique A Alias",
        "description": "second source",
        "external_references": [
            {"source_name": "mitre-attack", "external_id": "T1234"}
        ],
    }
    tool = {
        "type": "tool",
        "id": "tool--00000000-0000-4000-8000-000000000003",
        "name": "Tool A",
    }
    rel = {
        "type": "relationship",
        "id": "relationship--00000000-0000-4000-8000-000000000004",
        "relationship_type": "uses",
        "source_ref": tool["id"],
        "target_ref": ap2["id"],
    }

    fused = fuse_bundles([
        {"type": "bundle", "id": "bundle--1", "objects": [ap1]},
        {"type": "bundle", "id": "bundle--2", "objects": [ap2, tool, rel]},
    ])

    attack_patterns = [o for o in fused["objects"] if o.get("type") == "attack-pattern"]
    relationships = [o for o in fused["objects"] if o.get("type") == "relationship"]
    assert len(attack_patterns) == 1
    assert attack_patterns[0]["description"] == "second source"
    assert relationships[0]["target_ref"] == attack_patterns[0]["id"]
