"""A report containing a file hash must not abort Stage 2.

Nothing crossed this seam: hashes_to_stix_observed_data is reached only from
convert_ir_to_stix when the IR carries hashes, and no test produced one. A
blanket datetime.utcnow replacement wrote datetime.now(datetime.UTC) into a
module that does "from datetime import datetime", where that attribute does
not exist, so every such report raised AttributeError and took the whole
Stage 2 batch with it.
"""
import pytest
import stix2

from plugins.mcp.app.utilities.cti_linguistics import extract_hashes
from plugins.mcp.app.utilities.cti_mitre_extract import hashes_to_stix_observed_data


SHA256 = "a" * 64
TEXT = f"The dropper, SHA256 {SHA256}, was written to disk."


@pytest.fixture
def observed():
    hashes = extract_hashes(TEXT)
    assert hashes, "extract_hashes produced nothing to build from"
    return hashes_to_stix_observed_data(hashes)


def test_it_builds_without_raising(observed):
    assert observed and observed[0]["type"] == "observed-data"


def test_the_reference_parser_accepts_it(observed):
    # stix2.parse enforces the required properties. It rejected these for
    # missing first_observed and last_observed, so a bundle carrying any file
    # hash could not be loaded by a consumer at all.
    stix2.parse(observed[0], allow_custom=True)


@pytest.mark.parametrize("prop", [
    "type", "spec_version", "id", "created", "modified",
    "first_observed", "last_observed", "number_observed", "objects",
])
def test_required_properties_are_present(observed, prop):
    assert prop in observed[0]


def test_the_hash_survives_into_the_observable(observed):
    assert observed[0]["objects"]["0"]["hashes"]["SHA256"] == SHA256


def test_timestamps_are_consistent_within_one_object(observed):
    o = observed[0]
    assert o["created"] == o["modified"] == o["first_observed"] == o["last_observed"]
    assert o["created"].endswith("Z"), "STIX wants Z, not +00:00"
