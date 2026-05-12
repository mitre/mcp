import json

import pytest


def _rel(rid, rtype, source, target):
    return {
        "type": "relationship",
        "id": f"relationship--00000000-0000-4000-8000-{rid:012d}",
        "relationship_type": rtype,
        "source_ref": source,
        "target_ref": target,
    }


def test_topology_uses_infra_graph_network_services_software_and_targeted_users():
    from plugins.mcp.app.utilities.cti_topology_inference import build_range_topology

    actor = {
        "type": "threat-actor",
        "id": "threat-actor--00000000-0000-4000-8000-000000000001",
        "name": "Actor",
    }
    finance = {
        "type": "identity",
        "id": "identity--00000000-0000-4000-8000-000000000002",
        "name": "Finance",
        "identity_class": "organization",
    }
    user = {
        "type": "user-account",
        "id": "user-account--00000000-0000-4000-8000-000000000003",
        "user_id": "jdoe",
        "display_name": "jdoe",
    }
    infra = {
        "type": "infrastructure",
        "id": "infrastructure--00000000-0000-4000-8000-000000000004",
        "name": "File Server",
        "infrastructure_types": ["staging"],
        "x_cti_os": "windows",
    }
    traffic = {
        "type": "network-traffic",
        "id": "network-traffic--00000000-0000-4000-8000-000000000005",
        "dst_port": 445,
        "protocols": ["tcp"],
    }
    software = {
        "type": "software",
        "id": "software--00000000-0000-4000-8000-000000000006",
        "name": "Windows Server",
        "version": "2019",
        "vendor": "Microsoft",
        "cpe": "cpe:2.3:o:microsoft:windows_server_2019:1809:*:*:*:*:*:*:*",
    }
    ap = {
        "type": "attack-pattern",
        "id": "attack-pattern--00000000-0000-4000-8000-000000000007",
        "name": "LSASS Memory",
        "external_references": [
            {"source_name": "mitre-attack", "external_id": "T1003.001"}
        ],
    }

    bundle = {
        "type": "bundle",
        "id": "bundle--00000000-0000-4000-8000-000000000008",
        "objects": [
            actor, finance, user, infra, traffic, software, ap,
            _rel(9, "targets", actor["id"], finance["id"]),
            _rel(10, "uses", actor["id"], infra["id"]),
            _rel(11, "hosts", infra["id"], traffic["id"]),
            _rel(12, "hosts", infra["id"], software["id"]),
            _rel(13, "located-at", user["id"], finance["id"]),
            _rel(14, "uses", infra["id"], ap["id"]),
        ],
    }
    taxonomy = {
        "_raw_objects": [],
        "attack_id_index": {
            "T1003.001": {
                "name": "LSASS Memory",
                "x_mitre_platforms": ["Windows"],
                "x_mitre_permissions_required": ["User"],
                "kill_chain_phases": [
                    {"kill_chain_name": "mitre-attack", "phase_name": "credential-access"}
                ],
            }
        },
    }

    topology = build_range_topology(
        bundle,
        taxonomy,
        images_catalog=[{"name": "win2022", "os": "windows", "bootstrapped": True}],
    )

    assert topology["infrastructure_graph"]["reachable_infrastructure_refs"] == [infra["id"]]
    host = topology["hosts"][0]
    assert host["stix_id"] == infra["id"]
    assert host["reachable_from_roots"] is True
    assert "microsoft-ds" in host["services"]
    assert host["network_services"][0]["port"] == 445
    assert any(sw.get("cpe") == software["cpe"] for sw in host["software_required"])
    assert topology["network_edges"][0]["service"] == "microsoft-ds"
    assert topology["identities"][0]["targeted"] is True
    assert topology["user_accounts"][0]["organization_unit"] == "Finance"
    assert "Finance" in topology["user_accounts"][0]["ansible_role_input"]["user_tags"]
    assert topology["attack_surface"]["required_permissions"] == ["User"]
    assert "process" in topology["attack_surface"]["d3fend_artifacts"]


def test_deploy_spec_adds_topology_telemetry_and_operator_review():
    from plugins.mcp.app.utilities.cti_deploy_spec import synthesize_deploy_spec

    topology = {
        "type": "x-cti-range-topology",
        "id": "x-cti-range-topology--00000000-0000-4000-8000-000000000001",
        "primary_platform": "windows",
        "hosts": [{
            "name": "range-workstation",
            "role": "workstation",
            "platform": "windows",
            "services": ["microsoft-ds"],
            "software_required": [{"name": "ExampleAgent", "version": "1.0"}],
        }],
        "attack_surface": {
            "techniques": [{"technique_id": "T1003"}],
            "data_sources": ["Process", "Windows Registry"],
        },
        "network_edges": [],
        "user_accounts": [],
        "identities": [],
    }

    spec = synthesize_deploy_spec(
        topology,
        images_catalog=[{
            "name": "win2022",
            "os": "windows",
            "file": "win2022.qcow2",
            "provider": "microvm",
            "bootstrapped": True,
        }],
        range_roles=["sysmon", "winlogbeat", "microsoft-ds"],
        range_playbooks=[],
    )

    services = spec["images"][0]["host_meta"]["services"]
    assert "sysmon" in services
    assert "winlogbeat" in services
    assert spec["operator_review"]["score"] <= 1.0
    assert "operator_review_needed" in spec["operator_review"]
    assert spec["software_install_requests"][0]["name"] == "ExampleAgent"


def test_alphv_real_ae_plan_enrichment_materializes_plan_facts():
    import yaml
    from pathlib import Path
    from plugins.mcp.app.cti_pipeline_stage4_topology import (
        _enrich_topology_with_ae_plan,
        _technique_ids_in_bundle,
    )
    from plugins.mcp.app.utilities.cti_ae_library_loader import (
        ae_plan_to_stix,
        discover_ae_plans,
        find_plan_by_adversary,
        parse_ae_plan,
    )
    from plugins.mcp.app.utilities.cti_topology_inference import build_range_topology

    plan = find_plan_by_adversary(discover_ae_plans(), "alphv_blackcat")
    if not plan:
        pytest.skip("external AttackEvals AEL data is not installed")
    assert "attackevals-ael" in plan.get("library", "")
    ae_ir = parse_ae_plan(plan, taxonomy=None)
    bundle = ae_plan_to_stix(ae_ir, taxonomy=None)

    images_catalog = []
    for path in (
        Path("plugins/range/conf/onprem_microvm_images.yml"),
        Path("plugins/range/conf/onprem_images.yml"),
    ):
        if path.is_file():
            images_catalog.extend(
                (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("images") or []
            )

    topology = build_range_topology(bundle, {}, images_catalog=images_catalog)
    enriched = _enrich_topology_with_ae_plan(
        topology,
        plan,
        ae_ir,
        _technique_ids_in_bundle(bundle),
        images_catalog=images_catalog,
    )

    expected_hosts = {
        (h.get("hostname") or "").strip().lower()
        for h in ae_ir.get("infrastructure") or []
        if (h.get("hostname") or "").strip()
    }
    actual_hosts = {
        (h.get("hostname") or h.get("name") or "").strip().lower().removeprefix("range-")
        for h in enriched["hosts"]
    }
    assert expected_hosts <= actual_hosts
    assert not any("synthesized" in h for h in actual_hosts)
    assert any(h.get("role") == "dc" for h in enriched["hosts"])
    assert any(h.get("role") == "backup" for h in enriched["hosts"])
    assert set(enriched["emulation_plan"]["techniques"]) == {
        (ap.get("id") or "").upper()
        for ap in ae_ir.get("attack_patterns") or []
        if ap.get("id")
    }
    assert set(enriched["emulation_plan"]["software"]) == {
        (item.get("name") or "").strip().lower()
        for field in ("software", "malware", "tools")
        for item in ae_ir.get(field) or []
        if isinstance(item, dict) and (item.get("name") or "").strip()
    }
    assert set(enriched["emulation_plan"]["users"]) == {
        (u.get("username") or "").strip().lower()
        for u in ae_ir.get("user_accounts") or []
        if isinstance(u, dict) and (u.get("username") or "").strip()
    }
    assert set(ae_ir.get("file_paths") or []) <= set(enriched.get("file_paths") or [])
    assert set(ae_ir.get("registry_keys") or []) <= set(enriched.get("registry_keys") or [])


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


def test_knowledge_graph_persists_to_sqlite(tmp_path):
    from plugins.mcp.app.utilities.cti_knowledge_graph import persist_bundle_topology

    infra = {
        "type": "infrastructure",
        "id": "infrastructure--00000000-0000-4000-8000-000000000001",
        "name": "Host A",
    }
    bundle = {"type": "bundle", "id": "bundle--1", "objects": [infra]}
    topology = {
        "hosts": [{
            "name": "range-host-a",
            "stix_id": infra["id"],
            "role": "server",
            "platform": "linux",
        }],
        "network_edges": [],
    }

    result = persist_bundle_topology(bundle, topology, db_path=tmp_path / "kg.sqlite")
    assert result["nodes_seen"] >= 2
    assert (tmp_path / "kg.sqlite").is_file()
