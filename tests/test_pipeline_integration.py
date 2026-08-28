#!/usr/bin/env python3
"""
Integration tests for the CTI pipeline.

Verifies that:
1. Core imports work without errors
2. Offline IR extraction produces valid output
3. STIX builders produce spec-compliant objects
4. Technique extraction finds explicit T-numbers
9. Full pipeline processes a file end-to-end
10. STIX 2.1 compliance on output bundles

Run: python3 -m pytest tests/test_pipeline_integration.py -v
  or: python3 tests/test_pipeline_integration.py
"""

import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parents[1]))


# ============================================================
# 1. CORE IMPORTS
# ============================================================

def test_core_imports():
    """All pipeline modules import without error."""
    from plugins.mcp.app.utilities.nlp_model import get_nlp
    from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy
    from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
    from plugins.mcp.app.utilities.cti_stix_builders import make_threat_actor, make_attack_pattern
    assert get_nlp() is not None
    print("  ✓ All core imports successful")


# ============================================================
# 2. OFFLINE IR EXTRACTION
# ============================================================

def test_offline_ir_extraction():
    """Offline IR produces valid structure from sample text."""
    from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline

    text = """APT29 deployed Cobalt Strike beacons and used Mimikatz to dump
    credentials from LSASS memory. The group exploited CVE-2021-44228 for
    initial access and moved laterally via RDP."""

    ir = extract_ir_offline(text)

    assert isinstance(ir, dict)
    assert "threat_actors" in ir
    assert "malware" in ir
    assert "tools" in ir
    assert "behaviors" in ir
    assert isinstance(ir["tools"], list)
    # Should find at least Cobalt Strike or Mimikatz
    tool_names = {t.get("name", "").lower() for t in ir["tools"]}
    found_known = tool_names & {"cobalt strike", "mimikatz"}
    assert len(found_known) >= 1, f"Expected known tools, found: {tool_names}"
    print(f"  ✓ Offline IR: {len(ir['tools'])} tools, {len(ir['behaviors'])} behaviors")


# ============================================================
# 3. STIX BUILDERS
# ============================================================

def test_stix_builders_compliance():
    """STIX builders produce spec_version 2.1 compliant objects."""
    from plugins.mcp.app.utilities.cti_stix_builders import (
        make_threat_actor, make_attack_pattern,
    )
    from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy

    tax = load_mitre_taxonomy()

    ta = make_threat_actor({"name": "TestActor"})
    assert ta["spec_version"] == "2.1"
    assert ta["type"] == "threat-actor"
    assert "roles" not in ta or ta.get("roles") != ["threat-actor"]  # invalid role removed

    ap = make_attack_pattern("T1486", tax)
    assert ap["spec_version"] == "2.1"
    assert ap["name"]  # should have a name from taxonomy

    print("  ✓ All STIX builders produce spec_version 2.1")


# ============================================================
# 4. EXPLICIT T-NUMBER EXTRACTION
# ============================================================

def test_explicit_technique_extraction():
    """Regex extraction finds T-numbers in text."""
    from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text
    from plugins.mcp.app.utilities.cti_taxonomy_loader import build_normalized_attack_patterns

    _, lookup = build_normalized_attack_patterns()

    text = "The actor used T1486 for encryption and T1490 for recovery inhibition."
    ids = extract_ids_from_text(text, lookup)

    assert "T1486" in ids
    assert "T1490" in ids
    assert len(ids) == 2
    print(f"  ✓ Extracted {len(ids)} explicit technique IDs")



# ============================================================
# 9. FULL PIPELINE END-TO-END (OFFLINE)
# ============================================================

def test_full_pipeline_offline():
    """Full pipeline processes a CTI report end-to-end in offline mode."""
    import yaml

    base = Path(__file__).resolve().parents[1] / "data"
    clean_dir = base / "clean"

    # Find any clean file
    clean_files = list(clean_dir.glob("*.txt"))
    if not clean_files:
        print("  ⚠ No clean files found, skipping end-to-end test")
        return

    # Set offline mode
    conf = Path(__file__).resolve().parents[1] / "conf" / "local.yml"
    if conf.exists():
        cfg = yaml.safe_load(conf.read_text())
        was_offline = cfg.get("cti", {}).get("offline", False)
        cfg.setdefault("cti", {})["offline"] = True
        conf.write_text(yaml.dump(cfg))
    else:
        was_offline = True

    try:
        from plugins.mcp.app.cti_pipeline_stage1 import process_file

        ir_dir = base / "outputs_ir" / "pytest" / "debug"
        final_dir = base / "outputs_ir" / "pytest" / "complete"
        ir_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        f = clean_files[0]
        for old in list(ir_dir.glob(f"{f.stem}*")) + list(final_dir.glob(f"{f.stem}*")):
            old.unlink()

        asyncio.run(process_file(f, ir_dir, final_dir, None))

        # Verify output exists
        output = final_dir / f"{f.stem}.json"
        assert output.exists(), f"Pipeline didn't produce output for {f.name}"

        ir = json.loads(output.read_text())
        assert "attack_patterns" in ir
        assert "relationships" in ir
        assert "threat_actors" in ir or "malware" in ir or "tools" in ir

        print(f"  ✓ Full pipeline: {f.name} → {len(ir.get('attack_patterns',[]))} TTPs, "
              f"{len(ir.get('relationships',[]))} rels")
    finally:
        # Restore config
        if conf.exists():
            cfg["cti"]["offline"] = was_offline
            conf.write_text(yaml.dump(cfg))


# ============================================================
# 10. STIX OUTPUT COMPLIANCE
# ============================================================

def test_stix_output_compliance():
    """Verify STIX output objects have required fields."""
    base = Path(__file__).resolve().parents[1] / "data"

    # Find any STIX output
    stix_files = list((base / "outputs_stix").glob("*.stix.json")) if (base / "outputs_stix").exists() else []

    # Also check pipeline test output
    for d in (base / "outputs_ir").iterdir() if (base / "outputs_ir").exists() else []:
        if d.is_dir():
            stix_files.extend(d.glob("complete/*.json"))

    if not stix_files:
        print("  ⚠ No STIX outputs found, skipping compliance test")
        return

    f = stix_files[0]
    data = json.loads(f.read_text())

    # Check it's a valid IR/STIX structure
    if "objects" in data:
        # It's a STIX bundle
        for obj in data["objects"][:5]:
            assert "type" in obj
            if obj["type"] in ("malware", "tool", "threat-actor", "infrastructure"):
                assert "spec_version" in obj, f"Missing spec_version in {obj['type']}"
                assert obj["spec_version"] == "2.1"
    else:
        # It's an IR
        assert "attack_patterns" in data or "threat_actors" in data

    print(f"  ✓ STIX compliance verified on {f.name}")


# ============================================================
# RUNNER
# ============================================================

if __name__ == "__main__":
    tests = [
        test_core_imports,
        test_offline_ir_extraction,
        test_stix_builders_compliance,
        test_explicit_technique_extraction,
        test_full_pipeline_offline,
        test_stix_output_compliance,
    ]

    passed = 0
    failed = 0

    print(f"\nRunning {len(tests)} integration tests\n")

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ✗ {test.__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"RESULTS: {passed}/{len(tests)} passed, {failed} failed")
    print(f"{'='*50}")

    sys.exit(1 if failed else 0)
