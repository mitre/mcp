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
    assert "behaviors" in ir
    assert isinstance(ir["threat_actors"], list)
    assert ir["behaviors"], "offline extraction produced no behaviors"
    print(f"  Offline IR: {len(ir['threat_actors'])} actors, "
          f"{len(ir['behaviors'])} behaviors")


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
    """Stage 1 end to end on the committed fixture, no LLM.

    Uses tests/data and a temp tree rather than the plugin's live data/ and
    conf/local.yml: the previous version read whatever the operator happened
    to have staged and rewrote their config to force offline mode, leaving it
    mutated if anything raised in between.
    """
    import shutil
    import tempfile

    import numpy
    _ = numpy.ndarray

    import plugins.mcp.app.utilities.cti_parsing as cti_parsing
    from plugins.mcp.app.cti_pipeline_stage1 import process_file

    fixture = Path(__file__).resolve().parent / "data" / "blackcat-sample.txt"
    assert fixture.is_file(), "committed fixture is missing"

    async def _offline(*_a, **_k):
        return None

    original = cti_parsing.llm_generate
    cti_parsing.llm_generate = _offline
    try:
        base = Path(tempfile.mkdtemp())
        ir_dir = base / "debug"
        final_dir = base / "complete"
        ir_dir.mkdir(parents=True)
        final_dir.mkdir(parents=True)

        clean = base / "blackcat.txt"
        shutil.copy(fixture, clean)

        asyncio.run(process_file(clean, ir_dir, final_dir, None))
    finally:
        cti_parsing.llm_generate = original

    output = final_dir / "blackcat.json"
    assert output.exists(), "pipeline produced no IR"

    ir = json.loads(output.read_text())
    assert ir["attack_patterns"], "no techniques attributed"
    assert ir["provenance"]["extractor"] == "offline"
    print(f"  \u2713 Full pipeline: {len(ir['attack_patterns'])} TTPs")


# ============================================================
# 10. STIX OUTPUT COMPLIANCE
# ============================================================

# Built by our own builders, not read from data/, which is gitignored: on a
# clean checkout the old glob was empty and the test returned without asserting.
def test_stix_output_compliance(sample_stix_bundle):
    """The emitted bundle must satisfy the 2.1 spec, per the reference parser."""
    import stix2

    stix2.parse(sample_stix_bundle, allow_custom=True)

    assert sample_stix_bundle["type"] == "bundle"
    assert sample_stix_bundle["objects"], "bundle carries no objects"
    for obj in sample_stix_bundle["objects"]:
        assert obj["spec_version"] == "2.1", f"{obj['type']} is not 2.1"
        for prop in ("id", "created", "modified"):
            assert prop in obj, f"{obj['type']} is missing {prop}"


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
