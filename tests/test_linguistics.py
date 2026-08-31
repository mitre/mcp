"""Tests for cti_linguistics.py — linguistic extraction and matching."""



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












