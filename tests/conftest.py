"""
Pytest configuration and shared fixtures for MCP plugin tests.
"""
import sys
import json
import asyncio
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parents[1]))

MCP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MCP_ROOT / "data"
CLEAN_DIR = DATA_DIR / "clean"
TAXONOMY_PATH = MCP_ROOT / "app" / "utilities" / "cti_taxonomy" / "enterprise_attack.json"


@pytest.fixture(scope="session")
def nlp():
    """Shared spaCy model (loaded once per test session)."""
    from plugins.mcp.app.utilities.nlp_model import nlp
    return nlp


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
        make_malware, make_tool, make_threat_actor, make_bundle,
    )

    objects = [
        make_malware({"name": "TestMalware"}),
        make_tool({"name": "TestTool"}),
        make_threat_actor({"name": "TestActor"}),
    ]
    return make_bundle([o for o in objects if o])
