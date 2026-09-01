"""
Pytest configuration and shared fixtures for MCP plugin tests.
"""
import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parents[1]))

MCP_ROOT = Path(__file__).resolve().parents[1]
LOCAL_YML = MCP_ROOT / "conf" / "local.yml"
DATA_DIR = MCP_ROOT / "data"
CLEAN_DIR = DATA_DIR / "clean"
TAXONOMY_PATH = MCP_ROOT / "app" / "utilities" / "cti_taxonomy" / "enterprise_attack.json"


@pytest.fixture(autouse=True)
def _preserve_local_yml():
    """No test may leave the operator's conf/local.yml changed.

    Several suites POST to a running server, so their writes land in the real
    file. That is how a deployment ended up pinned to a gateway nobody chose,
    and the server rewrites the file with yaml.safe_dump, so the comments go
    too. set_config only merges, so a POST cannot undo one: the file has to be
    restored on disk.

    Autouse and unconditional, because the next suite to grow a live POST
    should not have to remember this.

    It restores the file, not the running server. set_config caches what it
    wrote, so a live POST kept being served from memory after the file was put
    back, the browser read it from /defaults, and the panel wrote it to disk
    again. The tests that did that are gone; this stays as the backstop.
    """
    before = LOCAL_YML.read_text(encoding="utf-8") if LOCAL_YML.exists() else None
    try:
        yield
    finally:
        after = LOCAL_YML.read_text(encoding="utf-8") if LOCAL_YML.exists() else None
        if after == before:
            return
        if before is None:
            LOCAL_YML.unlink(missing_ok=True)
        else:
            LOCAL_YML.write_text(before, encoding="utf-8")


# The live suites upload through the running server, so their fixtures land in
# the operator's real data/. Named pytest_* or test_* by convention; this
# sweeps whatever they leave.
_TEST_UPLOAD_PREFIXES = ("pytest_", "test_cti.")


@pytest.fixture(autouse=True)
def _sweep_test_uploads():
    yield
    for sub in ("raw/uploads", "raw/processed", "clean", "stix_cti",
                "outputs_stix", "outputs_ir/complete"):
        d = DATA_DIR / sub
        if not d.is_dir():
            continue
        # rglob, not iterdir: stage 2 writes its per-report debug copies to
        # outputs_stix/debug/, which a top-level sweep left behind.
        for f in d.rglob("*"):
            if f.is_file() and f.name.startswith(_TEST_UPLOAD_PREFIXES):
                f.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def nlp():
    """Shared spaCy model (loaded once per test session)."""
    from plugins.mcp.app.utilities.nlp_model import get_nlp
    return get_nlp()


@pytest.fixture(scope="session")
def taxonomy():
    """Shared MITRE taxonomy (loaded once per test session)."""
    from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy
    return load_mitre_taxonomy()


@pytest.fixture(scope="session")
def technique_lookup():
    """Shared technique lookup table."""
    from plugins.mcp.app.utilities.cti_taxonomy_loader import build_normalized_attack_patterns
    _, lookup = build_normalized_attack_patterns()
    return lookup


@pytest.fixture
def sample_text():
    """Sample CTI text for testing."""
    return """BlackCat operators leverage Mimikatz, LaZagne and WebBrowserPassView
    to recover stored passwords, as well as GO Simple Tunnel (GOST) and MEGAsync
    to exfiltrate data. The group used PsExec for lateral movement via RDP.
    Shadow copies were deleted using vssadmin. The ransomware encrypts files
    using AES and ChaCha20 encryption. Windows Defender was disabled."""


@pytest.fixture
def sample_ir():
    """Sample IR structure for testing."""
    return {
        "threat_actors": [{"name": "BlackCat", "description": "Ransomware group"}],
        "malware": [{"name": "BlackCat Ransomware", "description": "Rust-based ransomware"}],
        "tools": [
            {"name": "Mimikatz", "description": "Credential extraction"},
            {"name": "PsExec", "description": "Remote execution"},
            {"name": "LaZagne", "description": "Password recovery"},
        ],
        "infrastructure": [{"name": "Tor", "description": "Onion routing"}],
        "attack_patterns": [
            {"id": "T1486", "name": "Data Encrypted for Impact", "confidence": 0.9},
            {"id": "T1490", "name": "Inhibit System Recovery", "confidence": 0.8},
            {"id": "T1003.001", "name": "LSASS Memory", "confidence": 0.85},
        ],
        "behaviors": [{"description": "encrypt files using AES"}],
        "relationships": [],
    }


@pytest.fixture
def sample_stix_bundle():
    """Sample STIX 2.1 bundle for testing."""
    from plugins.mcp.app.utilities.cti_stix_builders import (
        make_attack_pattern, make_threat_actor, make_bundle,
    )
    from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy

    objects = [
        make_threat_actor({"name": "TestActor"}),
        make_attack_pattern({"id": "T1486"}, load_mitre_taxonomy()),
    ]
    return make_bundle([o for o in objects if o])
