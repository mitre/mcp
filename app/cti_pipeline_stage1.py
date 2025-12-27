#!/usr/bin/env python3
"""
Phase 1 — CTI → Intermediate Representation (IR)

This module contains ONLY execution logic for Stage 1.
All orchestration, CLI, and scenario routing lives in cti_ingest_svc.py.
"""

import json
import asyncio
from pathlib import Path
import spacy
from utilities.cti_relationships import vectorize, normalize_and_qualify_behaviors, extract_all_relationships, dedup_relationships

nlp = spacy.load("en_core_web_lg")

# ------------------------------------------------------------
# CTI Raw Text Cleaning and Extraction
# ------------------------------------------------------------
from utilities.cti_raw_cleaner import clean_raw_directory
from utilities.cti_parsing import extract_ir, render_ir_summary
from utilities.cti_mitre_extract import extract_mitre_techniques, convert_sets

from utilities.cti_relationships import (
    semantic_relationships,
    relationships_from_behaviors
)

from utilities.cti_taxonomy_loader import build_normalized_attack_patterns
from utilities.cti_linguistics import (
    normalize_behavior_text,
    canonicalize_relationship_endpoints,
    extract_dynamic_techniques
)

from utilities.cti_entity_validator import validate_entities, repair_entities
from utilities.cti_relationships import REL_REJECTIONS
from utilities.cti_mitre_extract import MITRE_DROPPED
# ------------------------------------------------------------
# NLP Enhancement Layers
# ------------------------------------------------------------
from utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
from utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer2

# ------------------------------------------------------------
# Directory Constants
# ------------------------------------------------------------
RAW_DIR_NAME    = "raw"
CLEAN_DIR_NAME  = "clean"
OUTPUTS_IR_DIR  = "outputs_ir"
IMAGES_DIR_NAME = "images"
ANALYST_VECTOR = vectorize("analyze observe report identify research highlight conclude")
ACTION_VECTOR = vectorize("execute deploy exfiltrate communicate install move load")


# ==============================================================
# Directory Setup
# ==============================================================

def ensure_dirs(base_dir: Path):
    raw_dir   = base_dir / RAW_DIR_NAME
    clean_dir = base_dir / CLEAN_DIR_NAME
    outputs   = base_dir / OUTPUTS_IR_DIR
    images    = base_dir / IMAGES_DIR_NAME
    for d in (raw_dir, clean_dir, outputs, images):
        d.mkdir(parents=True, exist_ok=True)
    return raw_dir, clean_dir, outputs, images

# ==============================================================
# Step 1 — raw → clean
# ==============================================================

def step_raw_to_clean(base_dir: Path):
    raw_dir, clean_dir, _, images_dir = ensure_dirs(base_dir)
    clean_raw_directory(base_dir, raw_dir, clean_dir, images_dir)

# ==============================================================
# Step 2 — clean → IR (FULL)
# ==============================================================

async def step_parse_to_ir(base_dir: Path, stop_after: str | None = None):
    _, clean_dir, outputs, _ = ensure_dirs(base_dir)

    ir_dir    = outputs / "debug_ir"
    rel_dir   = outputs / "debug_relationships"
    mitre_dir = outputs / "debug_mitre"
    final_dir = outputs / "complete"

    for d in (ir_dir, rel_dir, mitre_dir, final_dir):
        d.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(3)

    async def process_file(path: Path):
        REL_REJECTIONS.clear()

        async with sem:
            print(f"\n[*] Processing {path.name}")
            text = path.read_text(errors="ignore")

            # 1️⃣ IR
            ir = await load_or_extract_ir(path, text, ir_dir)
            if stop_after == "ir":
                return

            # 2️⃣ NLP cleanup
            pre_beh_count = len(ir.get("behaviors", []))

            ir = clean_ir_nlp_layer1(ir, text)
 
            post_beh_count = len(ir.get("behaviors", []))

            print(
                f"[IR][NLP] behaviors before={pre_beh_count} "
                f"after={post_beh_count}"
            )

            if post_beh_count < pre_beh_count:
                raise RuntimeError(
                    "[FATAL] NLP Layer 1 removed behaviors — forbidden"
                )

            # 3️⃣ Behaviors (CRITICAL)
            normalized, qualified = normalize_and_qualify_behaviors(ir)
            ir["behaviors"] = normalized
            ir["qualified_behaviors"] = qualified

            # 4️⃣ Relationships
            rels = await extract_all_relationships(text, ir, qualified)
            ir["relationships"] = dedup_relationships(rels)

            if stop_after == "relationships":
                return

            # 5️⃣ Entity validation
            ir = await validate_entities(ir, destructive=False)
            ir = repair_entities(ir)

            # 6️⃣ MITRE
            techniques, lookup = build_normalized_attack_patterns()
            ir = clean_ir_nlp_layer2(ir, {"attack_patterns": techniques})

            # cti_linguistics.extract_dynamic_techniques(text, techniques, behaviors=None, limit=25)
            ling = await extract_dynamic_techniques(
                text,
                techniques,
                ir.get("qualified_behaviors", []),
                limit=25
            )
            print(f"[LING] techniques_from_linguistics={len(ling)}")
            
            mitre = extract_mitre_techniques(
                text, qualified, techniques, lookup
            )

            seen = set()
            merged = []

            for t in ir.get("attack_patterns", []) + ling + mitre:
                if isinstance(t, dict) and t.get("id") and t["id"] not in seen:
                    seen.add(t["id"])
                    merged.append(t)

            ir["attack_patterns"] = merged

            # 7️⃣ Output
            final = convert_sets(ir)
            (final_dir / f"{path.stem}.json").write_text(
                json.dumps(final, indent=2), encoding="utf-8"
            )
            (final_dir / f"{path.stem}.txt").write_text(
                render_ir_summary(final), encoding="utf-8"
            )

    await asyncio.gather(*(process_file(p) for p in clean_dir.glob("*.txt")))
    print("\n[+] parse-to-ir complete.")

async def load_or_extract_ir(path: Path, text: str, ir_dir: Path) -> dict:
    ir_path = ir_dir / f"{path.stem}.ir-only.json"

    if ir_path.exists():
        ir = json.loads(ir_path.read_text())
        print(f"[IR] Resumed IR: {path.stem}")
        return ir

    ir = await extract_ir(text)
    ir = convert_sets(ir)

    ir_path.write_text(json.dumps(ir, indent=2), encoding="utf-8")
    (ir_dir / f"{path.stem}.ir-only.txt").write_text(
        render_ir_summary(ir), encoding="utf-8"
    )

    print(f"[IR] Extracted IR: {path.stem}")
    return ir

