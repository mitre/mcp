"""Tests for cti_linguistics.py — linguistic extraction and matching."""
import pytest
import numpy as np


class TestExtractCommands:
    def test_finds_windows_commands(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_commands
        text = "The attacker ran cmd.exe /c whoami on the target system."
        cmds = extract_commands(text)
        assert len(cmds) >= 1
        assert any("cmd.exe" in c["command"] for c in cmds)

    def test_finds_linux_commands(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_commands
        text = "Used chmod 777 /tmp/backdoor to set permissions."
        cmds = extract_commands(text)
        assert len(cmds) >= 1

    def test_empty_text(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_commands
        assert extract_commands("") == []
        assert extract_commands(None) == []

    def test_single_word_skipped(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_commands
        text = "The powershell.exe was found."
        cmds = extract_commands(text)
        # Single word commands should be skipped (need at least 2 words)
        assert all(len(c["command"].split()) >= 2 for c in cmds)


class TestExtractHashes:
    def test_finds_sha256(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_hashes
        text = "Hash: 0c6f444c6940a3688ffc6f8b9d5774c032e3551ebbccb64e4280ae7fc1fac479"
        hashes = extract_hashes(text)
        assert len(hashes) >= 1
        assert any(h["hash_type"] == "SHA256" for h in hashes)

    def test_finds_md5(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_hashes
        text = "MD5: d41d8cd98f00b204e9800998ecf8427e"
        hashes = extract_hashes(text)
        assert any(h["hash_type"] == "MD5" for h in hashes)

    def test_no_duplicates(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_hashes
        text = "Hash: abcd1234abcd1234abcd1234abcd1234\nHash: abcd1234abcd1234abcd1234abcd1234"
        hashes = extract_hashes(text)
        assert len(hashes) == 1

    def test_empty(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_hashes
        assert extract_hashes("") == []


class TestNormalizeBehaviorText:
    def test_basic(self):
        from plugins.mcp.app.utilities.cti_linguistics import normalize_behavior_text
        assert normalize_behavior_text("  Hello   World  ") == "hello world"

    def test_empty(self):
        from plugins.mcp.app.utilities.cti_linguistics import normalize_behavior_text
        assert normalize_behavior_text("") == ""


class TestFuzzyResolve:
    def test_finds_match(self):
        from plugins.mcp.app.utilities.cti_linguistics import fuzzy_resolve
        candidates = [{"name": "Mimikatz"}, {"name": "PsExec"}]
        result = fuzzy_resolve("mimikatz", candidates)
        assert result is not None
        assert result["name"] == "Mimikatz"

    def test_no_match(self):
        from plugins.mcp.app.utilities.cti_linguistics import fuzzy_resolve
        candidates = [{"name": "Mimikatz"}]
        result = fuzzy_resolve("completely_different", candidates)
        assert result is None

    def test_empty_name(self):
        from plugins.mcp.app.utilities.cti_linguistics import fuzzy_resolve
        assert fuzzy_resolve("", [{"name": "X"}]) is None
        assert fuzzy_resolve(None, []) is None


class TestPhraseVector:
    def test_returns_numpy_array(self):
        from plugins.mcp.app.utilities.cti_linguistics import phrase_vector
        v = phrase_vector("credential dumping")
        assert isinstance(v, np.ndarray)
        assert v.shape == (300,)

    def test_empty_returns_zeros(self):
        from plugins.mcp.app.utilities.cti_linguistics import phrase_vector
        v = phrase_vector("")
        assert np.allclose(v, np.zeros(300))


class TestCosine:
    def test_identical_vectors(self):
        from plugins.mcp.app.utilities.cti_linguistics import cosine
        v = np.array([1.0, 2.0, 3.0])
        assert abs(cosine(v, v) - 1.0) < 0.001

    def test_orthogonal(self):
        from plugins.mcp.app.utilities.cti_linguistics import cosine
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert abs(cosine(a, b)) < 0.001

    def test_zero_vector(self):
        from plugins.mcp.app.utilities.cti_linguistics import cosine
        a = np.zeros(3)
        b = np.array([1.0, 2.0, 3.0])
        assert cosine(a, b) == 0.0

    def test_none_input(self):
        from plugins.mcp.app.utilities.cti_linguistics import cosine
        assert cosine(None, np.array([1.0])) == 0.0


class TestExtractCandidatePhrases:
    def test_extracts_phrases(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_candidate_phrases
        text = "The malware encrypts files and exfiltrates data to cloud storage."
        phrases = extract_candidate_phrases(text)
        assert isinstance(phrases, list)
        assert len(phrases) >= 1

    def test_empty_text(self):
        from plugins.mcp.app.utilities.cti_linguistics import extract_candidate_phrases
        assert extract_candidate_phrases("") == []


class TestNormalizeEntityType:
    def test_finds_tool(self):
        from plugins.mcp.app.utilities.cti_linguistics import normalize_entity_type
        ir = {"tools": [{"name": "Mimikatz"}], "malware": [], "threat_actors": [],
              "infrastructure": [], "attack_patterns": []}
        assert normalize_entity_type("Mimikatz", ir) == "tool"

    def test_unknown(self):
        from plugins.mcp.app.utilities.cti_linguistics import normalize_entity_type
        ir = {"tools": [], "malware": [], "threat_actors": [],
              "infrastructure": [], "attack_patterns": []}
        assert normalize_entity_type("Unknown", ir) == "unknown"
