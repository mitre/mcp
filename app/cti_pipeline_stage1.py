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
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# =============================================================
# Core Utilities
# =============================================================

from utilities.cti_raw_cleaner import clean_raw_directory
from utilities.cti_parsing import extract_ir, render_ir_summary
from utilities.cti_mitre_extract import extract_mitre_techniques, convert_sets
from utilities.cti_taxonomy_loader import build_normalized_attack_patterns
from utilities.cti_entity_validator import validate_entities, repair_entities

from utilities.cti_relationships import (
    normalize_and_qualify_behaviors,
    extract_all_relationships,
    REL_REJECTIONS,
)

from utilities.cti_linguistics import extract_dynamic_techniques, extract_commands, extract_hashes

# =============================================================
# NLP Enhancement Layers
# =============================================================

from utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
from utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer2
from utilities.nlp.cti_behavior_expansion import recover_nominalized_behaviors

# =============================================================
# Directory Constants
# =============================================================

RAW_DIR_NAME    = "raw"
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
    raw_dir   = base_dir / RAW_DIR_NAME
    clean_dir = base_dir / CLEAN_DIR_NAME
    outputs   = base_dir / OUTPUTS_IR_DIR
    images    = base_dir / IMAGES_DIR_NAME

    for d in (raw_dir, clean_dir, outputs, images):
        d.mkdir(parents=True, exist_ok=True)

    return raw_dir, clean_dir, outputs, images

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
    raw_dir, clean_dir, _, images_dir = ensure_dirs(base_dir)
    clean_raw_directory(base_dir, raw_dir, clean_dir, images_dir)

# =============================================================
# Stage 1.2 — Clean → IR (PARALLEL)
# =============================================================

def step_parse_to_ir(base_dir: Path, stop_after: str | None = None):
    """
    Process all cleaned TXT files into IR + relationships + MITRE.

    Parallelism:
        • One OS process per file
        • Each worker loads its own NLP models
        • No shared state
    """
    start_time = time.perf_counter()

    _, clean_dir, outputs, _ = ensure_dirs(base_dir)

    ir_dir    = outputs / "debug_ir"
    final_dir = outputs / "complete"

    ir_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    files = list(clean_dir.glob("*.txt"))
    if not files:
        print("[!] No clean files found.")
        return

    workers = max(1, (os.cpu_count() or 4) - 1)
    print(f"[+] Stage1 starting: {len(files)} files | {workers} workers")

    # --------------------------------------------------
    # Submit ONE FILE PER PROCESS (no asyncio here)
    # --------------------------------------------------
    with ProcessPoolExecutor(max_workers=workers) as pool:
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

        for fut in as_completed(futures):
            path = futures[fut]
            try:
                fut.result()
                print(f"[OK] {path.name}")
            except Exception as e:
                print(f"[ERR] {path.name}: {e}")

    elapsed = time.perf_counter() - start_time
    print(f"\n[STAGE1] completed in {elapsed:.2f}s")

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
        3. Behavior normalization & qualification
        4. Relationship extraction
        5. Entity validation
        6. MITRE ATT&CK mapping
        7. Final JSON + analyst summary output
    """
    REL_REJECTIONS.clear()
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

    recovered = recover_nominalized_behaviors(text)
    if recovered:
        ir["behaviors"].extend(recovered)

    if len(ir["behaviors"]) < pre_beh:
        raise RuntimeError("NLP Layer 1 removed behaviors (forbidden)")

    # ---------------------------------------------------------
    # 3. Behavior qualification
    # ---------------------------------------------------------
    normalized, qualified = normalize_and_qualify_behaviors(ir)
    ir["behaviors"] = normalized
    ir["qualified_behaviors"] = qualified

    high_conf = [b for b in qualified if b.get("confidence", 0) >= 0.5]
    low_conf  = [b for b in qualified if b.get("confidence", 0) < 0.5]

    # ---------------------------------------------------------
    # 4. Relationships
    # ---------------------------------------------------------
    raw_relationships = await extract_all_relationships(
        text, ir, high_conf
    ) or []
    ir["relationships"] = rag_safe_relationships(raw_relationships)
    ir["low_confidence_behaviors"] = low_conf

    # ---------------------------------------------------------
    # Commands Extraction (Linguistic)
    # ---------------------------------------------------------

    commands = extract_commands(text)
    if commands:
        for m in ir.get("malware", []):
            if m.get("name", "").lower() in text.lower():
                _merge_commands(m, commands)

        for t in ir.get("tools", []):
            if t.get("name", "").lower() in text.lower():
                _merge_commands(t, commands)
    
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
    # 5. Entity validation
    # ---------------------------------------------------------
    ir = await validate_entities(ir, destructive=False)
    ir = repair_entities(ir)

    # ---------------------------------------------------------
    # 6. MITRE ATT&CK
    # ---------------------------------------------------------
    techniques, lookup = build_normalized_attack_patterns()
    ir = clean_ir_nlp_layer2(ir, {"attack_patterns": techniques})

    ling = await extract_dynamic_techniques(
        text,
        techniques,
        ir.get("qualified_behaviors", []),
        limit=25,
    )

    mitre = extract_mitre_techniques(
        text,
        qualified,
        techniques,
        lookup,
    )

    seen = set()
    merged = []
    for t in ir.get("attack_patterns", []) + ling + mitre:
        if isinstance(t, dict) and t.get("id") and t["id"] not in seen:
            seen.add(t["id"])
            merged.append(t)

    ir["attack_patterns"] = merged

    # ---------------------------------------------------------
    # 7. Output
    # ---------------------------------------------------------
    final = convert_sets(ir)

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

    # Load spaCy per worker (MANDATORY)
    import spacy
    try:
        spacy.load("en_core_web_lg")
    except OSError:
        pass

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
        print(f"[IR] Resumed {path.stem}")
        return json.loads(ir_path.read_text())

    ir = await extract_ir(text)
    ir = convert_sets(ir)

    ir_path.write_text(json.dumps(ir, indent=2), encoding="utf-8")
    (ir_dir / f"{path.stem}.ir-only.txt").write_text(
        render_ir_summary(ir),
        encoding="utf-8",
    )

    print(f"[IR] Extracted {path.stem}")
    return ir

def _merge_commands(entity, commands):
    existing = {c["command"] for c in entity.get("x_cti_commands", [])}
    for c in commands:
        if c["command"] not in existing:
            entity.setdefault("x_cti_commands", []).append(c)

def rag_safe_relationships(rels: list[dict], min_conf: float = 0.55) -> list[dict]:
    """
    Filter relationships for RAG suitability.

    Constraints:
      • confidence ≥ min_conf
      • source_context ∈ {behavior, sentence}
    """
    return [
        r for r in rels
        if r.get("confidence", 0.0) >= min_conf
        and r.get("source_context") in {"behavior", "sentence"}
    ]
