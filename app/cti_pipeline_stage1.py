#!/usr/bin/env python3
"""
Phase 1 — CTI → Intermediate Representation (IR)

This module contains ONLY execution logic for Stage 1.
All orchestration, CLI, and scenario routing lives in cti_ingest_svc.py.
"""

import json
import asyncio
from pathlib import Path

# ------------------------------------------------------------
# CTI Raw Text Cleaning and Extraction
# ------------------------------------------------------------
from utilities.cti_raw_cleaner import clean_raw_directory
from utilities.cti_parsing import extract_ir, render_ir_summary
from utilities.cti_mitre_extract import extract_mitre_techniques, convert_sets

from utilities.cti_relationships import (
    semantic_relationships,
    normalize_llm_relationships,
    repair_llm_relationship_dicts,
    pattern_based_relationships,
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
from utilities.nlp.cti_relationship_recovery import clean_ir_nlp_layer2
from utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer3

# ------------------------------------------------------------
# Directory Constants
# ------------------------------------------------------------
RAW_DIR_NAME    = "raw"
CLEAN_DIR_NAME  = "clean"
OUTPUTS_IR_DIR  = "outputs_ir"
IMAGES_DIR_NAME = "images"

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

    ir_dir     = outputs / "debug_ir"
    rel_dir    = outputs / "debug_relationships"
    mitre_dir  = outputs / "debug_mitre"
    final_dir  = outputs / "complete"

    for d in (ir_dir, rel_dir, mitre_dir, final_dir):
        d.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(3)

    async def process_file(path: Path):
        async with sem:
            print(f"\n[*] Processing: {path.name}")
            txt = path.read_text(errors="ignore")

            # -----------------------------
            # Resume or extract IR
            # -----------------------------
            ir_path = ir_dir / f"{path.stem}.ir-only.json"
            if ir_path.exists():
                ir = json.loads(ir_path.read_text())
                print(f"[RESUME] Loaded IR for {path.stem}")
            else:
                ir = await extract_ir(txt)
                ir = convert_sets(ir)
                ir_path.write_text(json.dumps(ir, indent=2), encoding="utf-8")
                (ir_dir / f"{path.stem}.ir-only.txt").write_text(
                    render_ir_summary(ir), encoding="utf-8"
                )

            if stop_after == "ir":
                return

            # -----------------------------
            # NLP cleanup layers
            # -----------------------------
            ir = clean_ir_nlp_layer1(ir, txt)
            ir = clean_ir_nlp_layer2(ir, txt)

            # -----------------------------
            # Relationship extraction (MUST happen before validation)
            # -----------------------------
            print("    → Extracting relationships…")

            rel_sem = await semantic_relationships(txt, ir)
            rel_beh = relationships_from_behaviors(ir.get("behaviors", []), ir)

            try:
                rel_llm = await normalize_llm_relationships(
                    ir.get("relationships", []), ir
                )
                rel_llm = repair_llm_relationship_dicts(rel_llm, ir)
            except Exception:
                rel_llm = []

            try:
                rel_pat = pattern_based_relationships(txt, ir)
            except Exception:
                rel_pat = []

            all_rel = rel_sem + rel_beh + rel_llm + rel_pat
            ir["relationships"] = canonicalize_relationship_endpoints(ir, all_rel)

            # -----------------------------
            # NOW validate entities (safe)
            # -----------------------------
            ir = await validate_entities(ir)

            ir = repair_entities(ir)

            # Preserve extracted actors; augment with inferred
            existing = ir.get("threat_actors", [])
            existing_names = {
                a.get("name","").lower()
                for a in existing if a.get("name")
            }

            inferred = infer_threat_actors(ir)
            for a in inferred:
                n = a.get("name","").lower()
                if n and n not in existing_names:
                    existing.append(a)
                    existing_names.add(n)

            ir["threat_actors"] = existing

            # Filter relationships to valid entities
            valid_entities = {
                e.get("name","").lower()
                for g in ("threat_actors","malware","tools","infrastructure")
                for e in ir.get(g, [])
                if e.get("name")
            }

            # Analyst rule:
            # Keep relationship if EITHER endpoint is still valid
            ir["relationships"] = [
                r for r in ir.get("relationships", [])
                if (
                    r.get("source","").lower() in valid_entities
                    and (
                        r.get("target","").lower() in valid_entities
                        or r.get("target","").startswith("<")
                    )
                )
            ]


            # Debug relationships
            try:
                (rel_dir / f"{path.stem}.relationships.rejected.json").write_text(
                    json.dumps(REL_REJECTIONS, indent=2), encoding="utf-8"
                )
            except Exception:
                pass

            rel_dump = convert_sets(ir)
            (rel_dir / f"{path.stem}.relationships.json").write_text(
                json.dumps(rel_dump, indent=2), encoding="utf-8"
            )
            (rel_dir / f"{path.stem}.relationships.txt").write_text(
                "\n".join(
                    f"{r['source']} {r['relationship']} {r['target']}"
                    for r in ir.get("relationships", [])
                ),
                encoding="utf-8"
            )

            if stop_after == "relationships":
                return

            # -----------------------------
            # MITRE enrichment (unchanged)
            # -----------------------------
            techniques, lookup = build_normalized_attack_patterns()

            clean_behaviors = []
            for b in ir.get("behaviors", []):
                raw = b.get("text") if isinstance(b, dict) else str(b)
                if not raw:
                    continue

                norm = normalize_behavior_text(raw)
                if not norm:
                    continue

                clean_behaviors.append({
                    "text": norm,
                    "description": norm,
                    "confidence": b.get("confidence", 0.6),
                    "source": b.get("source", "llm"),
                })

            ir["behaviors"] = clean_behaviors
            ir = clean_ir_nlp_layer3(ir, {"attack_patterns": techniques})

            ling = extract_dynamic_techniques(txt, techniques)
            mitre = extract_mitre_techniques(
                txt, ir.get("behaviors", []), techniques, lookup
            )

            seen, merged = set(), []
            for t in ir.get("attack_patterns", []) + ling + mitre:
                if isinstance(t, dict):
                    tid = t.get("id")
                    if not tid:
                        continue
                    entry = t
                elif isinstance(t, str):
                    tid = t
                    entry = {"id": tid, "name": tid}
                else:
                    continue

                if tid not in seen:
                    seen.add(tid)
                    merged.append(entry)

            ir["attack_patterns"] = [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "confidence": round(min(float(t.get("confidence",0.0)),1.0),2),
                    "evidence": t.get("evidence") or t.get("source_context") or "",
                }
                for t in merged
            ]

            final = convert_sets(ir)
            (final_dir / f"{path.stem}.json").write_text(
                json.dumps(final, indent=2), encoding="utf-8"
            )
            (final_dir / f"{path.stem}.txt").write_text(
                render_ir_summary(final), encoding="utf-8"
            )

    await asyncio.gather(*(process_file(p) for p in clean_dir.glob("*.txt")))
    print("\n[+] parse-to-ir complete.")

# ==============================================================
# Threat Actor Inference
# ==============================================================

def infer_threat_actors(ir: dict) -> list[dict]:
    """
    Augment actors based on relationships.
    MUST NOT remove or gate existing actors.
    """
    if not ir.get("relationships"):
        return []

    malware = {m["name"].lower() for m in ir.get("malware", []) if m.get("name")}
    tools   = {t["name"].lower() for t in ir.get("tools", []) if t.get("name")}
    infra   = {i["name"].lower() for i in ir.get("infrastructure", []) if i.get("name")}

    malicious_targets = malware | tools | infra

    malicious_sources = {
        r.get("source","").lower()
        for r in ir.get("relationships", [])
        if r.get("target","").lower() in malicious_targets
    }

    return [
        a for a in ir.get("threat_actors", [])
        if a.get("name","").lower() in malicious_sources
    ]
