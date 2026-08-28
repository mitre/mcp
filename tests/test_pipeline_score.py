"""Score pipeline output against the committed measuring stick.

Runs stage 1 offline on a committed BlackCat report and diffs the ATT&CK
technique ids it produces against data/measuring-sticks/. Keys on
external_references external_id, never on STIX object ids, which
regenerate every run.

The fixture names its technique ids explicitly, so recall here is an upper
bound rather than a field estimate. Precision is the number that regresses
when an extraction source starts emitting noise, and is why this exists.
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

_HERE = Path(__file__).resolve().parent
_PLUGIN = _HERE.parent
_FIXTURE = _HERE / "data" / "blackcat-sample.txt"
_STICK = _PLUGIN / "data" / "measuring-sticks" / "blackcat-expected.stix.json"

# Floors, not exact values, set with headroom so an unrelated taxonomy
# refresh does not trip them. Measured at the time of writing:
# precision 0.825, recall 0.971, F1 0.892.
MIN_PRECISION = 0.75
MIN_RECALL = 0.85
MIN_F1 = 0.80


def _expected_technique_ids() -> set:
    bundle = json.loads(_STICK.read_text(encoding="utf-8"))
    return {
        ref["external_id"]
        for obj in bundle.get("objects", [])
        if obj.get("type") == "attack-pattern"
        for ref in obj.get("external_references", []) or []
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id")
    }


@pytest.fixture(scope="module")
def stage1_run():
    """Stage 1 output for the committed fixture, no LLM involved.

    Returns (technique_ids, stdout). The output is captured here rather than
    with capfd in a test, because this fixture is module-scoped and runs
    during the first test that uses it, so a later test's capfd sees nothing.
    """
    import numpy
    _ = numpy.ndarray

    import plugins.mcp.app.utilities.cti_parsing as cti_parsing

    async def _offline(*_a, **_k):
        return None

    original = cti_parsing.llm_generate
    cti_parsing.llm_generate = _offline
    try:
        from plugins.mcp.app.cti_pipeline_stage1 import (
            step_parse_to_ir,
            step_raw_to_clean,
        )

        base = Path(tempfile.mkdtemp())
        uploads = base / "raw" / "uploads"
        uploads.mkdir(parents=True)
        shutil.copy(_FIXTURE, uploads / "blackcat.txt")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            step_raw_to_clean(base)
            step_parse_to_ir(base)
        captured = buf.getvalue()

        produced = list((base / "outputs_ir" / "complete").glob("*.json"))
        assert produced, "stage 1 produced no IR"
        ir = json.loads(produced[0].read_text(encoding="utf-8"))
    finally:
        cti_parsing.llm_generate = original

    ids = {
        ap["id"]
        for ap in ir.get("attack_patterns", [])
        if isinstance(ap, dict) and ap.get("id")
    }
    return ids, captured


@pytest.fixture(scope="module")
def pipeline_technique_ids(stage1_run):
    return stage1_run[0]


def _score(got: set, expected: set) -> dict:
    tp = len(got & expected)
    precision = tp / len(got) if got else 0.0
    recall = tp / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"n": len(got), "tp": tp, "precision": precision, "recall": recall, "f1": f1}


def test_scores_above_the_floor(pipeline_technique_ids):
    expected = _expected_technique_ids()
    s = _score(pipeline_technique_ids, expected)
    print(
        f"\n  n={s['n']} tp={s['tp']} "
        f"P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f}"
        f"\n  false positives: {sorted(pipeline_technique_ids - expected)}"
        f"\n  missed:          {sorted(expected - pipeline_technique_ids)}"
    )
    assert s["precision"] >= MIN_PRECISION, f"precision regressed to {s['precision']:.3f}"
    assert s["recall"] >= MIN_RECALL, f"recall regressed to {s['recall']:.3f}"
    assert s["f1"] >= MIN_F1, f"F1 regressed to {s['f1']:.3f}"


def test_emits_no_revoked_techniques(pipeline_technique_ids):
    """The linguistic source used to reach revoked ids through a taxonomy
    that does not filter them. Named explicitly so a regression is obvious."""
    revoked = {"T1017", "T1076", "T1109", "T1064", "T1086"}
    assert not (pipeline_technique_ids & revoked)


def test_stick_and_pipeline_agree_on_the_key(pipeline_technique_ids):
    """Every id on both sides is an ATT&CK external_id, not a STIX uuid."""
    for tid in pipeline_technique_ids | _expected_technique_ids():
        assert tid.startswith("T"), tid
        assert "--" not in tid, tid


def test_grounding_and_platform_filter_actually_run(stage1_run):
    """Both steps sit inside try/except, so a NameError in them degrades
    silently. A deleted variable once left both dead for every document
    while the scores still passed."""
    out = stage1_run[1]
    assert out, "stage 1 produced no output to inspect"
    for warn in ("[TECHNIQUE-GROUND][WARN]", "[TECHNIQUE-FILTER][WARN]",
                 "[TAXONOMY][WARN]"):
        assert warn not in out, f"a pipeline step degraded silently: {warn}"
    # Positive assertions: absence of a warning is not evidence a step ran.
    assert "[TECHNIQUE-GROUND] grounded=" in out
    assert "[TECHNIQUE-FILTER] attested=" in out
