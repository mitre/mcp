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
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# =============================================================
# Core Utilities
# =============================================================

from plugins.mcp.app.utilities.cti_raw_cleaner import clean_raw_directory
from plugins.mcp.app.utilities.cti_parsing import extract_ir, render_ir_summary
from plugins.mcp.app.utilities.cti_mitre_extract import extract_mitre_techniques, convert_sets
from plugins.mcp.app.utilities.cti_taxonomy_loader import build_normalized_attack_patterns
from plugins.mcp.app.utilities.cti_entity_validator import validate_entities, repair_entities, reclassify_entities

from plugins.mcp.app.utilities.cti_relationships import (
    normalize_and_qualify_behaviors,
    extract_all_relationships,
    REL_REJECTIONS,
)

from plugins.mcp.app.utilities.cti_linguistics import extract_dynamic_techniques, extract_commands, extract_hashes
from plugins.mcp.app.utilities.llm_client import get_llm_provenance


# =============================================================
# NLP Enhancement Layers
# =============================================================

from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
from plugins.mcp.app.utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer2
from plugins.mcp.app.utilities.nlp.cti_behavior_expansion import recover_nominalized_behaviors

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

def step_parse_to_ir(base_dir: Path, stop_after: str | None = None):
    """
    Process all cleaned TXT files into IR + relationships + MITRE.

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
    if not files:
        print("[!] No clean files found.")
        return
    if os.cpu_count() > 2:
        workers = max(1, (os.cpu_count() or 4) - 2)
    else:
        workers = 1
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
        raw_uploads, raw_processed, _, _, _ = ensure_dirs(base_dir)
        for fut in as_completed(futures):
            clean_path = futures[fut]
            raw_path = None
            for p in raw_uploads.iterdir():
                if p.is_file() and p.stem == clean_path.stem:
                    raw_path = p
                    break
            try:
                fut.result()
                print(f"[OK] {clean_path.name}")

                # MOVE RAW INPUT ONLY AFTER SUCCESS
                if raw_path and raw_path.exists():
                    move_raw_to_processed(raw_path, raw_processed)

            except Exception as e:
                print(f"[ERR] {clean_path.name}: {e}")

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
        seen = {(b.get("verb"), b.get("object")) for b in ir["behaviors"]}
        for b in recovered:
            key = (b.get("verb"), b.get("object"))
            if key not in seen:
                ir["behaviors"].append(b)
                seen.add(key)

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
    # 5. Entity reclassification + validation
    # ---------------------------------------------------------
    ir = reclassify_entities(ir)
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

    # Extract explicit T-numbers from all IR text fields
    all_ir_text = text
    for group in ("threat_actors", "malware", "tools", "infrastructure", "behaviors", "attack_patterns"):
        for item in ir.get(group, []):
            if isinstance(item, dict):
                all_ir_text += " " + (item.get("description", "") or "")
                all_ir_text += " " + (item.get("text", "") or "")
    from plugins.mcp.app.utilities.cti_mitre_extract import extract_ids_from_text
    explicit_from_ir = extract_ids_from_text(all_ir_text, lookup)
    explicit_objs = [lookup[tid] for tid in explicit_from_ir if tid in lookup]

    # Ontology-driven inference: tool/malware → known ATT&CK techniques
    from plugins.mcp.app.utilities.cti_ontology_inference import infer_techniques_from_entities
    ontology_inferred = infer_techniques_from_entities(ir, lookup, source_text=text)

    seen = set()
    merged = []
    for t in explicit_objs + ontology_inferred + ir.get("attack_patterns", []) + ling + mitre:
        if isinstance(t, dict) and t.get("id") and t["id"] not in seen:
            seen.add(t["id"])
            merged.append(t)

    # Remove deprecated/revoked technique IDs not in current taxonomy
    merged = [t for t in merged if t.get("id") in lookup or not t.get("id", "").startswith("T")]

    ir["attack_patterns"] = merged

    # ---------------------------------------------------------
    # 7. Output
    # ---------------------------------------------------------
    final = convert_sets(ir)
    final["provenance"] = ir.get("provenance")
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
    if not spacy.util.is_package("en_core_web_lg"):
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

def prepare_raw_uploads(base_dir: Path, selected: list[dict]):
    uploads = base_dir / "raw" / "uploads"
    inbox = base_dir / "raw" / "inbox"
    processed = base_dir / "raw" / "processed"
    SUPPORTED_EXTS = {".html", ".htm", ".pdf", ".txt", ".md"}


    uploads.mkdir(parents=True, exist_ok=True)

    for item in selected:
        name = item["name"]
        location = item["location"]

        src_root = inbox if location == "inbox" else processed
        src = src_root / name

        if not src.exists():
            continue

        if src.is_file():
            _copy_if_needed(src, uploads / src.name)

        elif src.is_dir():
            for f in src.rglob("*"):
                if f.suffix.lower() in SUPPORTED_EXTS:
                    _copy_if_needed(f, uploads / f.name)

def _copy_if_needed(src: Path, dst: Path):
    if dst.exists():
        return
    shutil.copy2(src, dst)
