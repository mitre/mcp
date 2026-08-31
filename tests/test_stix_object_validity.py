"""Emitted STIX must carry the properties the 2.1 spec requires.

The two enriched lookup paths hand-copied a field list that omitted created
and modified while the fallback set them, so a bundle was internally
inconsistent and stix2.parse fabricated the timestamps from the wall clock on
every read.
"""
import pytest

from plugins.mcp.app.utilities.cti_stix_builders import make_attack_pattern


TAXONOMY = {
    "attack_id_index": {
        "T1059": {
            "id": "attack-pattern--aaaaaaaa-0000-4000-8000-000000000001",
            "name": "Command and Scripting Interpreter",
            "created": "2017-05-31T21:30:49.546Z",
            "modified": "2023-04-01T00:00:00.000Z",
            "description": "d",
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1059"}],
        }
    },
    "name_index": {
        "attack-pattern:process injection": (
            "attack-pattern",
            "attack-pattern--aaaaaaaa-0000-4000-8000-000000000002",
            {
                "name": "Process Injection",
                "created": "2017-01-01T00:00:00.000Z",
                "modified": "2020-01-01T00:00:00.000Z",
                "description": "d",
                "external_references": [{"source_name": "mitre-attack", "external_id": "T1055"}],
            },
        )
    },
}


@pytest.mark.parametrize("ttp", [
    {"id": "T1059"},
    {"name": "Process Injection"},
    {"name": "Not A Real Technique"},
])
def test_every_path_sets_the_required_timestamps(ttp):
    ap = make_attack_pattern(ttp, TAXONOMY)
    assert ap["created"], f"{ttp} produced no created"
    assert ap["modified"], f"{ttp} produced no modified"


def test_the_attack_timestamps_are_preserved_not_restamped():
    # Restamping makes the bundle differ on every run for objects that did not
    # change, which is what made bundles non-idempotent.
    ap = make_attack_pattern({"id": "T1059"}, TAXONOMY)
    assert ap["created"] == "2017-05-31T21:30:49.546Z"
    assert ap["modified"] == "2023-04-01T00:00:00.000Z"


class TestNameLookupIsReachable:
    """name_index is keyed '<kind>:<lowername>'; a bare name matched nothing."""

    def test_a_name_only_technique_resolves_to_the_mitre_object(self):
        ap = make_attack_pattern({"name": "Process Injection"}, TAXONOMY)
        assert ap["id"] == "attack-pattern--aaaaaaaa-0000-4000-8000-000000000002"

    def test_it_carries_external_references(self):
        # Without these the object is invisible to _bundle_technique_ids and
        # therefore absent from adversary authoring entirely.
        ap = make_attack_pattern({"name": "Process Injection"}, TAXONOMY)
        assert ap["external_references"][0]["external_id"] == "T1055"

    def test_case_and_padding_do_not_matter(self):
        ap = make_attack_pattern({"name": "  PROCESS injection "}, TAXONOMY)
        assert ap["external_references"][0]["external_id"] == "T1055"

    def test_an_unknown_name_still_falls_back(self):
        ap = make_attack_pattern({"name": "Not A Real Technique"}, TAXONOMY)
        assert ap["name"] == "Not A Real Technique"
        assert ap["external_references"] == []
