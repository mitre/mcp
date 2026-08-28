"""Does fusing several reports raise technique recall?

Recall is the weakest number in the pipeline and it is a coverage problem:
one report describes part of what an actor does. This scores two partial
views of the same actor separately, then fused, against the committed
measuring stick.
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


def test_fusion_raises_recall_over_either_report(partial_reports):
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
