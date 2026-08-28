"""Does fusing several reports raise technique recall?

Recall is the weakest number in the pipeline and it is a coverage problem:
one report describes part of what an actor does.

Scope, stated plainly: the first three tests build bundles directly and
prove only that fuse_bundles unions technique ids and dedupes them. They
are mechanism tests, not measurements, and cannot fail because pipeline
recall regressed. test_fusion_of_two_real_reports_raises_recall is the one
that measures, because it runs the extractor over two halves of a real
report and scores the result against the committed stick.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

_PLUGIN = Path(__file__).resolve().parents[1]
_STICK = _PLUGIN / "data" / "measuring-sticks" / "blackcat-expected.stix.json"


def _expected() -> set:
    bundle = json.loads(_STICK.read_text(encoding="utf-8"))
    return {
        ref["external_id"]
        for obj in bundle.get("objects", [])
        if obj.get("type") == "attack-pattern"
        for ref in obj.get("external_references", []) or []
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id")
    }


def _bundle_of(technique_ids):
    """A minimal stage-2 shaped bundle carrying these techniques."""
    return {
        "type": "bundle",
        "id": "bundle--test",
        "objects": [
            {
                "type": "attack-pattern",
                "id": f"attack-pattern--{i:08d}-0000-0000-0000-000000000000",
                "spec_version": "2.1",
                "name": tid,
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": tid}
                ],
            }
            for i, tid in enumerate(sorted(technique_ids))
        ],
    }


def _technique_ids(bundle) -> set:
    return {
        ref["external_id"]
        for obj in bundle.get("objects", [])
        if obj.get("type") == "attack-pattern"
        for ref in obj.get("external_references", []) or []
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id")
    }


@pytest.fixture(scope="module")
def partial_reports():
    """Two disjoint halves of the stick, standing in for two reports that
    each describe part of what the actor does."""
    expected = sorted(_expected())
    return _bundle_of(expected[::2]), _bundle_of(expected[1::2])


def test_fusion_is_a_union_not_an_intersection(partial_reports):
    from plugins.mcp.app.utilities.cti_fusion import fuse_bundles

    expected = _expected()
    first, second = partial_reports

    r_first = len(_technique_ids(first) & expected) / len(expected)
    r_second = len(_technique_ids(second) & expected) / len(expected)

    fused = fuse_bundles([first, second])
    r_fused = len(_technique_ids(fused) & expected) / len(expected)

    print(
        f"\n  report A recall: {r_first:.3f}"
        f"\n  report B recall: {r_second:.3f}"
        f"\n  fused recall:    {r_fused:.3f}"
    )
    assert r_fused > r_first
    assert r_fused > r_second
    assert r_fused == pytest.approx(1.0)


def test_fusion_does_not_duplicate_a_shared_technique():
    from plugins.mcp.app.utilities.cti_fusion import fuse_bundles

    shared = _bundle_of(["T1486", "T1490"])
    overlapping = _bundle_of(["T1490", "T1489"])

    fused = fuse_bundles([shared, overlapping])

    assert _technique_ids(fused) == {"T1486", "T1489", "T1490"}
    attack_patterns = [
        o for o in fused["objects"] if o.get("type") == "attack-pattern"
    ]
    assert len(attack_patterns) == 3, "a technique present in both was duplicated"


def test_fusion_of_one_bundle_is_a_no_op():
    from plugins.mcp.app.utilities.cti_fusion import fuse_bundles

    only = _bundle_of(["T1486", "T1490"])
    assert _technique_ids(fuse_bundles([only])) == {"T1486", "T1490"}


def _extract(text: str) -> set:
    """Technique ids the real extractor finds in this text, no LLM."""
    from plugins.mcp.app.utilities.cti_offline_ir import extract_ir_offline
    from plugins.mcp.app.utilities.cti_taxonomy_loader import (
        build_normalized_attack_patterns,
    )
    from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text

    _, lookup = build_normalized_attack_patterns()
    ir = extract_ir_offline(text)
    found = set(extract_ids_from_text(text, lookup))
    found |= {
        ap.get("id")
        for ap in ir.get("attack_patterns", [])
        if isinstance(ap, dict) and ap.get("id")
    }
    return {t for t in found if t}


def test_fusion_of_two_real_reports_raises_recall():
    """The measuring test: split a real report in half, extract from each
    half independently, and check the union beats either half alone."""
    import numpy
    _ = numpy.ndarray

    from plugins.mcp.app.utilities.cti_fusion import fuse_bundles

    fixture = Path(__file__).resolve().parent / "data" / "blackcat-sample.txt"
    text = fixture.read_text(encoding="utf-8")
    lines = text.splitlines()
    half = len(lines) // 2
    first_text = "\n".join(lines[:half])
    second_text = "\n".join(lines[half:])

    expected = _expected()
    a, b = _extract(first_text), _extract(second_text)
    fused = _technique_ids(fuse_bundles([_bundle_of(a), _bundle_of(b)]))

    r_a = len(a & expected) / len(expected)
    r_b = len(b & expected) / len(expected)
    r_fused = len(fused & expected) / len(expected)

    print(
        f"\n  first half recall:  {r_a:.3f} ({len(a)} techniques)"
        f"\n  second half recall: {r_b:.3f} ({len(b)} techniques)"
        f"\n  fused recall:       {r_fused:.3f} ({len(fused)} techniques)"
    )
    assert r_fused > r_a
    assert r_fused > r_b
    assert fused >= (a | b) - {t for t in (a | b) if not t}
