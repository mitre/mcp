#!/usr/bin/env python3
"""
Phase 1 — CTI → Intermediate Representation (IR)

PURPOSE
-------
This module implements **Stage 1 execution only**:
    raw CTI → cleaned text → high-fidelity Intermediate Representation (IR)

It is intentionally:
    • Non-interactive
    • Deterministic
    • Parallelized (process-level)
    • Side-effect isolated per file

All orchestration, CLI flags, and pipeline routing
live in **cti_ingest_svc.py**.

DESIGN GUARANTEES
-----------------
• Each CTI document is processed in complete isolation
• No shared mutable state between workers
• spaCy + NLP models are loaded per worker
• Failures do not corrupt other files
• Output is always JSON-safe and resumable
"""

import json
import asyncio
import time
import os
import traceback
from pathlib import Path
from concurrent.futures import as_completed

# =============================================================
# Core Utilities
# =============================================================

from plugins.mcp.app.utilities.cti_raw_cleaner import clean_raw_directory, clean_stem
from plugins.mcp.app.utilities.cti_parsing import extract_ir, render_ir_summary
from plugins.mcp.app.utilities.cti_mitre_extract import extract_mitre_techniques, convert_sets
from plugins.mcp.app.utilities.cti_taxonomy_loader import (
    build_normalized_attack_patterns,
    load_mitre_taxonomy,
)

from plugins.mcp.app.utilities.cti_linguistics import extract_hashes
from plugins.mcp.app.utilities.cti_technique_grounding import (
    ground_techniques,
    detect_platforms,
    filter_techniques_by_platform,
    collapse_parent_techniques,
)
from plugins.mcp.app.utilities.llm_client import get_llm_provenance


# =============================================================
# NLP Enhancement Layers
# =============================================================

from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1

# =============================================================
# Directory Constants
# =============================================================

RAW_ROOT_DIR = "raw"
RAW_UPLOADS_DIR = "uploads"
RAW_PROCESSED_DIR = "processed"

CLEAN_DIR_NAME  = "clean"
OUTPUTS_IR_DIR  = "outputs_ir"
IMAGES_DIR_NAME = "images"

# =============================================================
# Directory Setup
# =============================================================

def ensure_dirs(base_dir: Path):
    """
    Create and return all directories required for Stage 1.

    Returns:
        (raw_dir, clean_dir, outputs_dir, images_dir)
    """
    raw_root      = base_dir / RAW_ROOT_DIR
    raw_uploads   = raw_root / RAW_UPLOADS_DIR
    raw_processed = raw_root / RAW_PROCESSED_DIR

    clean_dir = base_dir / CLEAN_DIR_NAME
    outputs   = base_dir / OUTPUTS_IR_DIR
    images    = base_dir / IMAGES_DIR_NAME

    for d in (raw_uploads, raw_processed, clean_dir, outputs, images):
        d.mkdir(parents=True, exist_ok=True)

    return raw_uploads, raw_processed, clean_dir, outputs, images

# =============================================================
# Stage 1.1 — Raw → Clean
# =============================================================

def step_raw_to_clean(base_dir: Path):
    """
    Convert raw CTI sources into normalized text.

    • HTML → extracted prose
    • PDF  → pdftotext
    • TXT  → copied
    • Images → copied

    No NLP occurs here.
    """
    raw_uploads, _, clean_dir, _, images_dir = ensure_dirs(base_dir)
    clean_raw_directory(base_dir, raw_uploads, clean_dir, images_dir)


def move_raw_to_processed(raw_path: Path, processed_dir: Path):
    target = processed_dir / raw_path.name
    if target.exists():
        return
    raw_path.rename(target)

# =============================================================
# Stage 1.2 — Clean → IR (PARALLEL)
# =============================================================

def step_parse_to_ir(base_dir: Path, stop_after: str | None = None,
                     only: list[str] | None = None):
    """
    Process all cleaned TXT files into IR + MITRE techniques.

    Parallelism:
        • One OS process per file
        • Each worker loads its own NLP models
        • No shared state
    """
    start_time = time.perf_counter()
    _, _, clean_dir, outputs, _ = ensure_dirs(base_dir)



    ir_dir    = outputs / "debug_ir"
    final_dir = outputs / "complete"

    ir_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    files = list(clean_dir.glob("*.txt"))

    # clean/ is never emptied, so it holds every report ever ingested. Without
    # this, selecting one row re-ran LLM extraction over the whole corpus while
    # the UI reported one file. An empty selection still means everything, which
    # is what the CLI and a full re-run want.
    if only:
        wanted = {clean_stem(name) for name in only}
        files = [f for f in files if f.stem in wanted]

    if not files:
        print("[!] No clean files found.")
        return
    if os.cpu_count() > 2:
        workers = max(1, (os.cpu_count() or 4) - 2)
    else:
        workers = 1

    # Stage1 work is LLM/IO-bound, not CPU-bound: each file makes
    # remote calls to the LLM gateway, downloads embeddings, reads
    # taxonomy data, etc. Use ThreadPoolExecutor instead of
    # ProcessPoolExecutor so we don't fork-from-a-multithreaded
    # FastMCP process (which deadlocks the workers — they inherit
    # the FastMCP reader-thread locks but not the thread, and any
    # acquisition blocks forever). Threads share the GIL but
    # release it on every IO call, so the LLM round-trips overlap
    # cleanly. The original print message keeps the same shape so
    # operators don't see a behaviour change in the log.
    from concurrent.futures import ThreadPoolExecutor as _Executor
    print(f"[+] Stage1 starting: {len(files)} files | {workers} workers")

    # --------------------------------------------------
    # Submit ONE FILE PER PROCESS (no asyncio here)
    # --------------------------------------------------
    with _Executor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process_one_file_sync,
                path,
                ir_dir,
                final_dir,
                stop_after,
            ): path
            for path in files
        }
        raw_uploads, raw_processed, _, _, _ = ensure_dirs(base_dir)
        succeeded = 0
        failures = []
        for fut in as_completed(futures):
            clean_path = futures[fut]
            raw_path = None
            for p in raw_uploads.iterdir():
                # Matching on the bare stem paired report.md with the clean
                # file report.txt actually produced from report.txt, so the
                # wrong raw file was moved to processed.
                if p.is_file() and clean_stem(p.name) == clean_path.stem:
                    raw_path = p
                    break
            try:
                fut.result()
                succeeded += 1
                print(f"[OK] {clean_path.name}")

                # MOVE RAW INPUT ONLY AFTER SUCCESS
                if raw_path and raw_path.exists():
                    move_raw_to_processed(raw_path, raw_processed)

            except Exception as e:
                failures.append((clean_path.name, e))
                print(f"[ERR] {clean_path.name}: {e}")
                print(traceback.format_exc())

    elapsed = time.perf_counter() - start_time
    print(f"\n[STAGE1] completed {succeeded}, failed {len(failures)} in {elapsed:.2f}s")

    # Callers keyed off the IR directory being empty, which reported a
    # missing-IR error rather than the exception that actually stopped the run.
    if failures and not succeeded:
        name, exc = failures[0]
        raise RuntimeError(f"Stage 1 failed for all {len(failures)} files; {name}: {exc}") from exc

# =============================================================
# Per-File Pipeline
# =============================================================

async def process_file(
        path: Path,
        ir_dir: Path,
        final_dir: Path,
        stop_after: str | None,
    ):
    """
    Full Stage-1 pipeline for a single CTI document.

    Steps:
        1. IR extraction / resume
        2. NLP Layer 1 cleanup
        3. MITRE ATT&CK mapping
        4. Final JSON + analyst summary output
    """
    print(f"\n[*] Processing {path.name}")

    text = path.read_text(errors="ignore")

    # ---------------------------------------------------------
    # 1. IR extraction
    # ---------------------------------------------------------
    ir = await load_or_extract_ir(path, text, ir_dir)
    if stop_after == "ir":
        return

    # ---------------------------------------------------------
    # 2. NLP Layer 1
    # ---------------------------------------------------------
    pre_beh = len(ir.get("behaviors", []))
    ir = clean_ir_nlp_layer1(ir, text)

    if len(ir["behaviors"]) < pre_beh:
        raise RuntimeError("NLP Layer 1 removed behaviors (forbidden)")

    # ---------------------------------------------------------
    # Commands Extraction (Linguistic)
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # Hash Extraction (File Observables)
    # ---------------------------------------------------------
    hashes = extract_hashes(text)
    if hashes:
        if hashes:
            ir.setdefault("hashes", [])
            seen = {(h["hash_type"], h["hash"]) for h in ir["hashes"]}
            for h in hashes:
                key = (h["hash_type"], h["hash"])
                if key not in seen:
                    ir["hashes"].append(h)


    # ---------------------------------------------------------
    # 3. MITRE ATT&CK
    # ---------------------------------------------------------
    techniques, lookup = build_normalized_attack_patterns()

    # Steps 3.5 and 3.6 below need the full taxonomy rather than the
    # normalized attack patterns.
    try:
        taxonomy = load_mitre_taxonomy()
    except Exception as e:
        print(f"[TAXONOMY][WARN] {e}")
        taxonomy = None

    mitre = extract_mitre_techniques(
        text,
        ir.get("behaviors", []),
        techniques,
        lookup,
    )

    # ---------------------------------------------------------
    # 3.5 Explicit-anchor technique grounding
    #
    # Walk a set of STRUCTURAL ANCHORS (binary names, system
    # commands, narrative phrases) and resolve each to an ATT&CK
    # technique via the loaded taxonomy. No hardcoded T-id table:
    # each anchor's resolver-key is a technique-NAME fragment that
    # we look up against attack_id_index at runtime. Adds the
    # canonical Windows TTPs (PowerShell, LSASS, vssadmin, mstsc,
    # net.exe, mimikatz, ...) that the vector-based MITRE pass
    # routinely misses, and prefers non-revoked + exact-name
    # matches so we don't pick deprecated IDs (T1086 over
    # T1059.001).
    # ---------------------------------------------------------
    try:
        grounded = ground_techniques(text, taxonomy=taxonomy)
    except Exception as e:
        print(f"[TECHNIQUE-GROUND][WARN] {e}")
        grounded = []
    print(f"[TECHNIQUE-GROUND] grounded={len(grounded)} techniques from "
          f"structural anchors")

    seen = set()
    merged = []
    # The linguistic source is deliberately absent: measured on the committed
    # BlackCat stick it contributed 21 false positives and zero true
    # positives, including three revoked ATT&CK ids, because it emits
    # techniques with no platforms key that the filter then keeps.
    for t in ir.get("attack_patterns", []) + mitre + grounded:
        if isinstance(t, dict) and t.get("id") and t["id"] not in seen:
            seen.add(t["id"])
            merged.append(t)

    # ---------------------------------------------------------
    # 3.6 Platform-attestation filter
    #
    # Drop techniques whose `x_mitre_platforms` doesn't overlap
    # the platform set attested in the source text. Stops
    # macOS-only / Linux-only techniques from polluting a
    # Windows-only CTI report. Platform vocabulary itself comes
    # from ATT&CK's `x_mitre_platforms` walks.
    # ---------------------------------------------------------
    try:
        attested = detect_platforms(text, taxonomy=taxonomy)
        if attested:
            before = len(merged)
            merged = filter_techniques_by_platform(merged, attested)
            print(f"[TECHNIQUE-FILTER] attested={sorted(attested)} "
                  f"kept={len(merged)} dropped={before - len(merged)}")
    except Exception as e:
        print(f"[TECHNIQUE-FILTER][WARN] {e}")

    # Parent-sub collapsing: keep T1059.001 over T1059 when both
    # appear -- ATT&CK consumers cite the most-specific reference.
    try:
        before = len(merged)
        merged = collapse_parent_techniques(merged)
        if before > len(merged):
            print(f"[TECHNIQUE-COLLAPSE] dropped {before - len(merged)} "
                  f"parents superseded by sub-techniques")
    except Exception as e:
        print(f"[TECHNIQUE-COLLAPSE][WARN] {e}")

    ir["attack_patterns"] = merged

    # ---------------------------------------------------------
    # 4. Output
    # ---------------------------------------------------------
    final = convert_sets(ir)
    provenance = dict(ir.get("provenance") or {})
    # Which extractor actually produced the IR. The model can be configured and
    # still return nothing, in which case the deterministic extractor ran and
    # crediting the model would be wrong.
    provenance["extractor"] = ir.get("extractor", "unknown")
    final["provenance"] = provenance
    (final_dir / f"{path.stem}.json").write_text(
        json.dumps(final, indent=2),
        encoding="utf-8",
    )

    (final_dir / f"{path.stem}.txt").write_text(
        render_ir_summary(final),
        encoding="utf-8",
    )

# =============================================================
# Worker Entry Point (SYNC)
# =============================================================

def process_one_file_sync(path, ir_dir, final_dir, stop_after):
    """
    ProcessPoolExecutor-safe entry point.

    This function:
        • Runs in its own OS process
        • Loads NLP models locally
        • Executes the async pipeline via asyncio.run()
    """

    # The model is not on PyPI under its own name, so pip alone does not
    # supply it. This check existed but its body was `pass`, so the real
    # failure was an OSError raised from inside spacy.load, several frames
    # deep in a worker, naming nothing the operator could act on.
    import spacy
    if not spacy.util.is_package("en_core_web_lg"):
        raise RuntimeError(
            "spaCy model en_core_web_lg is not installed. Run: "
            "python -m spacy download en_core_web_lg"
        )

    asyncio.run(process_file(path, ir_dir, final_dir, stop_after))

# =============================================================
# IR Resume / Extraction Helper
# =============================================================

async def load_or_extract_ir(path: Path, text: str, ir_dir: Path) -> dict:
    """
    Load cached IR if present; otherwise extract fresh IR.

    Guarantees:
        • Deterministic resume
        • JSON-safe output
    """
    ir_path = ir_dir / f"{path.stem}.ir-only.json"

    if ir_path.exists():
        with ir_path.open("r", encoding="utf-8") as f:
            cached_ir = json.load(f)

        cached_prov = cached_ir.get("provenance")
        current_prov = get_llm_provenance(profile="cti")

        if cached_prov == current_prov:
            print(f"[SKIP] IR up-to-date: {ir_path.name}")
            return cached_ir

        print(f"[REGEN] IR provenance changed: {ir_path.name}")

    ir = await extract_ir(text)
    ir = convert_sets(ir)
    ir["provenance"] = get_llm_provenance(profile="cti")
    ir_path.write_text(json.dumps(ir, indent=2), encoding="utf-8")
    (ir_dir / f"{path.stem}.ir-only.txt").write_text(
        render_ir_summary(ir),
        encoding="utf-8",
    )

    print(f"[IR] Extracted {path.stem}")
    return ir




