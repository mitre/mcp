"""Tests for cti_raw_cleaner.py — raw file cleaning and text extraction."""
import pytest


class TestExtractCleanTextFromHtml:
    def test_basic_html(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import extract_clean_text_from_html_sync
        html = "<html><body><p>This is a CTI report about APT29.</p></body></html>"
        text = extract_clean_text_from_html_sync(html)
        assert "APT29" in text or "CTI report" in text

    def test_empty_html(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import extract_clean_text_from_html_sync
        text = extract_clean_text_from_html_sync("")
        assert isinstance(text, str)


class TestShannonEntropy:
    def test_low_entropy(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import _shannon_entropy
        assert _shannon_entropy("aaaaaaa") < 1.0

    def test_high_entropy(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import _shannon_entropy
        assert _shannon_entropy("abcdefghijklmnop") > 2.0

    def test_empty(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import _shannon_entropy
        assert _shannon_entropy("") == 0.0


class TestIsCodeBlob:
    def test_code(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import _is_code_blob
        code = "function test() { return x + y; } var a = b.c;"
        assert isinstance(_is_code_blob(code), bool)

    def test_prose(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import _is_code_blob
        prose = "The threat actor deployed ransomware across the network infrastructure."
        assert _is_code_blob(prose) is False


@pytest.mark.asyncio
class TestProcessRawFile:
    async def test_markdown_is_cleaned_as_text(self, tmp_path):
        from plugins.mcp.app.utilities.cti_raw_cleaner import process_raw_file

        raw = tmp_path / "blackcat-report.md"
        clean = tmp_path / "clean"
        images = tmp_path / "images"
        clean.mkdir()
        images.mkdir()
        raw.write_text(
            "# ALPHV BlackCat\n\nThe intrusion used ransomware against a Windows file server.",
            encoding="utf-8",
        )

        result = await process_raw_file(raw, clean, images)

        assert "[TEXT]" in result
        assert (clean / "blackcat-report.md").read_text(encoding="utf-8").startswith("# ALPHV")
