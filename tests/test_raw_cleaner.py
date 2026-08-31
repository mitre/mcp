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
        # Normalised to .txt so Stage 1, which globs clean/*.txt, can find it,
        # and carrying the source extension so it cannot collide with a
        # same-named .txt or .pdf report.
        out = clean / "blackcat-report_md.txt"
        assert out.read_text(encoding="utf-8").startswith("# ALPHV")
        assert not (clean / "blackcat-report.md").exists()
        assert list(clean.glob("*.txt")), "Stage 1 would find nothing to parse"


class TestCleanNamesAreInjective:
    """Two sources must never clean to one file.

    Every branch wrote <stem>.txt, so report.md and report.txt both became
    report.txt. The cleaner gathers files concurrently, so whichever finished
    second replaced the other and an interleaved pair could produce text
    belonging to neither. Everything downstream is keyed on this stem, so the
    two reports also collapsed onto one IR and one bundle.
    """

    def test_the_extension_is_folded_in(self):
        from plugins.mcp.app.utilities.cti_raw_cleaner import clean_stem
        assert clean_stem("report.md") != clean_stem("report.txt")
        assert clean_stem("report.html") != clean_stem("report.pdf")

    @pytest.mark.asyncio
    async def test_a_md_and_txt_pair_both_survive(self, tmp_path):
        from plugins.mcp.app.utilities.cti_raw_cleaner import clean_raw_directory_async

        raw = tmp_path / "raw"
        clean = tmp_path / "clean"
        images = tmp_path / "images"
        for d in (raw, clean, images):
            d.mkdir()

        # Distinct sizes so a truncated or spliced result is detectable.
        (raw / "delta-report.md").write_text("M" * 6000, encoding="utf-8")
        (raw / "delta-report.txt").write_text("T" * 4000, encoding="utf-8")

        await clean_raw_directory_async(raw, clean, images)

        produced = sorted(p.name for p in clean.glob("*.txt"))
        assert len(produced) == 2, f"one source was lost: {produced}"

        bodies = {p.name: p.read_text(encoding="utf-8") for p in clean.glob("*.txt")}
        for name, body in bodies.items():
            assert set(body) in ({"M"}, {"T"}), f"{name} is spliced from both sources"
        assert {len(b) for b in bodies.values()} == {6000, 4000}
