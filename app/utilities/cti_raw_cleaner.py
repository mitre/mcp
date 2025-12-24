"""
cti_raw_cleaner.py

Async-capable raw → clean extractor used across Stage1.

    - HTML → cleaned TXT
    - PDF  → extracted text (async pdftotext)
    - TXT  → copied/normalized
    - Images copied
"""

import re
import asyncio
from pathlib import Path
import trafilatura
from bs4 import BeautifulSoup
import aiofiles
import aiofiles.os
import aiofiles.ospath

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

async def pdf_to_text(path: Path) -> str:
    async with SEMAPHORE:
        proc = await asyncio.create_subprocess_exec(
            "pdftotext",
            "-layout",
            str(path),
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return out.decode(errors="ignore") if out else ""

# ============================================================
# Process a single raw file
# ============================================================

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

        out = clean_dir / (path.stem + ".txt")
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(cleaned)

        return f"[HTML] {path.name} → {out.name}"

    # ---------------------------------------------------------
    # PDF
    # ---------------------------------------------------------
    if ext == ".pdf":
        cleaned = await pdf_to_text(path)

        if not cleaned.strip():
            return f"[SKIP] Empty PDF: {path.name}"

        out = clean_dir / (path.stem + ".txt")
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(cleaned)

        return f"[PDF] {path.name} → {out.name}"

    # ---------------------------------------------------------
    # TXT
    # ---------------------------------------------------------
    if ext == ".txt":
        async with aiofiles.open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = await f.read()

        if not txt.strip():
            return f"[SKIP] Empty TXT: {path.name}"

        out = clean_dir / path.name
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(txt)

        return f"[TXT] Copied {path.name}"

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

    results = await asyncio.gather(*tasks)

    for line in results:
        print("   ", line)

    print("[+] Async raw-to-clean complete.")


# ============================================================
# Sync wrapper for Stage1
# ============================================================

def clean_raw_directory(base_dir: Path, raw_dir: Path, clean_dir: Path, images_dir: Path):
    """
    Stage1-compatible wrapper.
    """
    return asyncio.run(clean_raw_directory_async(raw_dir, clean_dir, images_dir))
