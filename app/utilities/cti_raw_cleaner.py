"""
cti_raw_cleaner.py

Async-capable raw → clean extractor used across Stage1.

    - HTML → cleaned TXT
    - PDF  → extracted text (async pdftotext)
    - TXT/MD → copied/normalized
    - Images copied
"""

import re
import asyncio
from pathlib import Path, PurePath
import trafilatura
from bs4 import BeautifulSoup
import aiofiles
import aiofiles.os
import aiofiles.ospath
import math
# import spacy


# Limit async concurrency
SEMAPHORE = asyncio.Semaphore(8)

# ============================================================
# HTML CLEANING (sync helper)
# ============================================================

def extract_clean_text_from_html_sync(html: str) -> str:
    txt = trafilatura.extract(html)
    if txt:
        return "\n".join(l.strip() for l in txt.splitlines() if l.strip())

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    out = []
    for p in soup.find_all("p"):
        out.append(p.get_text().strip())
    for li in soup.find_all("li"):
        out.append("• " + li.get_text().strip())
    for t in soup.find_all("table"):
        out.append("[Table]")
        for tr in t.find_all("tr"):
            row = " | ".join(
                td.get_text().strip() for td in tr.find_all(["td", "th"])
            )
            out.append(row)

    clean = "\n".join(o for o in out if o.strip())
    return re.sub(r"\n{3,}", "\n\n", clean)


async def extract_clean_text_from_html(path: Path) -> str:
    async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = await f.read()

    # run CPU-heavy parse in thread pool
    return await asyncio.to_thread(extract_clean_text_from_html_sync, html)


# ============================================================
# PDF extraction (async)
# ============================================================

class PdfToolMissing(RuntimeError):
    """pdftotext is not on PATH. Raised so the caller can report which
    dependency is absent rather than surfacing a bare FileNotFoundError that
    reads like the report itself went missing."""


async def pdf_to_text(path: Path) -> str:
    async with SEMAPHORE:
        try:
            proc = await asyncio.create_subprocess_exec(
                "pdftotext",
                "-layout",
                str(path),
                "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            # pdftotext ships with poppler and is not a pip dependency, so a
            # stock install has no PDF support until it is installed.
            raise PdfToolMissing(
                "pdftotext not found. Install poppler "
                "(brew install poppler, or apt install poppler-utils) "
                "to ingest PDF reports."
            ) from e

        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"pdftotext failed on {path.name}: "
                f"{err.decode(errors='ignore')[:200]}"
            )
        return out.decode(errors="ignore") if out else ""

# ============================================================
# Process a single raw file
# ============================================================

def clean_stem(src_name: str) -> str:
    """The clean-file stem for a source filename, one source to one stem.

    Every branch used to write <stem>.txt, so report.md and report.txt both
    became report.txt: whichever finished second replaced the other, and
    because the cleaner gathers files concurrently a pair could interleave
    into text belonging to neither. Everything downstream is keyed on this
    stem, so the two reports also collapsed onto one IR and one bundle.

    Folding the extension in keeps it injective for any two distinct source
    names that both carry an extension, which upload enforces.
    """
    src = PurePath(src_name)
    ext = src.suffix.lstrip(".").lower()
    return f"{src.stem}_{ext}" if ext else src.stem


async def process_raw_file(path: Path, clean_dir: Path, images_dir: Path):
    ext = path.suffix.lower()

    # ---------------------------------------------------------
    # Images: direct copy
    # ---------------------------------------------------------
    if ext in (".png", ".jpg", ".jpeg", ".gif"):
        out = images_dir / path.name
        out.write_bytes(path.read_bytes())
        return f"[IMG] Copied {path.name}"

    # ---------------------------------------------------------
    # HTML
    # ---------------------------------------------------------
    if ext in (".html", ".htm"):
        cleaned = await extract_clean_text_from_html(path)

        if not cleaned.strip():
            return f"[SKIP] Empty HTML: {path.name}"

        out = clean_dir / (clean_stem(path.name) + ".txt")
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(cleaned)

        return f"[HTML] {path.name} → {out.name}"

    # ---------------------------------------------------------
    # PDF
    # ---------------------------------------------------------
    if ext == ".pdf":
        # Every other branch reports its outcome as a string, so a missing
        # poppler reports the same way instead of raising through the gather
        # and discarding the whole batch's results.
        try:
            cleaned = await pdf_to_text(path)
        except (PdfToolMissing, RuntimeError) as e:
            return f"[ERR] {path.name}: {e}"

        if not cleaned.strip():
            return f"[SKIP] Empty PDF: {path.name}"

        out = clean_dir / (clean_stem(path.name) + ".txt")
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(cleaned)

        return f"[PDF] {path.name} → {out.name}"

    # ---------------------------------------------------------
    # TXT / Markdown
    # ---------------------------------------------------------
    if ext in (".txt", ".md"):
        async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = await f.read()

        if not txt.strip():
            return f"[SKIP] Empty TXT: {path.name}"

        # -------------------------------------------------
        # Linguistic dominance gate
        # -------------------------------------------------
        if _is_code_blob(txt) and not _is_linguistically_dominant(txt):
            return f"[SKIP] Code-dominant TXT: {path.name}"

        # -------------------------------------------------
        # Filename sanity gate
        # -------------------------------------------------
        stem = path.stem.strip()
        if not re.search(r"[a-zA-Z]{3,}", stem):
            return f"[SKIP] Non-document filename: {path.name}"

        # Normalised like the html and pdf branches. Keeping the original
        # extension meant a .md upload landed in clean/ as .md, and Stage 1
        # globs *.txt, so the file was accepted by three UI surfaces and never
        # parsed.
        out = clean_dir / (clean_stem(path.name) + ".txt")
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(txt)

        return f"[TEXT] Copied {path.name}"


    return f"[SKIP] Unsupported type: {path.name}"


# ============================================================
# Full async directory processor
# ============================================================

async def clean_raw_directory_async(raw_dir: Path, clean_dir: Path, images_dir: Path):
    print("[+] Async raw → clean extraction starting…")

    tasks = [
        process_raw_file(path, clean_dir, images_dir)
        for path in raw_dir.rglob("*")
        if path.is_file()
    ]
    print(f"[DEBUG] raw_dir={raw_dir}")
    print(f"[DEBUG] clean_dir={clean_dir}")
    print(f"[DEBUG] images_dir={images_dir}")
    # One unhandled failure used to discard every other file's result.
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for line in results:
        if isinstance(line, BaseException):
            print(f"    [ERR] {type(line).__name__}: {line}")
        else:
            print("   ", line)
    clean_count = len(list(clean_dir.glob("*.txt")))
    print(f"[DEBUG] clean txt count={clean_count}")

    print("[+] Async raw-to-clean complete.")


# ============================================================
# Sync wrapper for Stage1
# ============================================================

def clean_raw_directory(base_dir: Path, raw_dir: Path, clean_dir: Path, images_dir: Path):
    """
    Stage1-compatible wrapper.
    """
    return asyncio.run(clean_raw_directory_async(raw_dir, clean_dir, images_dir))

def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    probs = [v / len(s) for v in freq.values()]
    return -sum(p * math.log2(p) for p in probs)


def _is_linguistically_dominant(text: str) -> bool:
    """
    Returns True if prose dominates over code.

    Allows:
    - CTI reports with embedded code
    Rejects:
    - Code-only or minified blobs
    """
    # Resolved inside the function to avoid fork corruption.
    from plugins.mcp.app.utilities.nlp_model import get_nlp

    doc = get_nlp()(text)

    word_tokens = [t for t in doc if t.is_alpha]
    verb_tokens = [t for t in doc if t.pos_ == "VERB"]
    sentence_count = len(list(doc.sents))

    # No linguistic structure
    if sentence_count < 2:
        return False

    # Too few verbs → not explanatory prose
    if len(verb_tokens) < 2:
        return False

    # Extremely low word ratio = code dominant
    if len(word_tokens) / max(len(doc), 1) < 0.25:
        return False

    return True


def _is_code_blob(text: str) -> bool:
    """
    Detects minified / executable-dominant content using entropy.
    """
    entropy = _shannon_entropy(text)

    # Minified JS / packed code is very high entropy
    if entropy > 4.8:
        return True

    return False

