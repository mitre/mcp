#!/usr/bin/env python3
"""
Phase 1 — CTI → Intermediate Representation (IR)

This module contains ONLY execution logic for Stage 1.
All orchestration, CLI, and scenario routing lives in cti_ingest_svc.py.
"""

import json
import re
import asyncio
from pathlib import Path

# ------------------------------------------------------------
# CTI Raw Text Cleaning and Extraction
# ------------------------------------------------------------
from utilities.cti_raw_parser import parse_raw_cti
from utilities.cti_raw_cleaner import clean_raw_directory

from utilities.cti_parsing import extract_ir, render_ir_summary
from utilities.cti_mitre_extract import extract_mitre_techniques, convert_sets
from utilities.cti_relationships import (
    semantic_relationships,
    normalize_llm_relationships,
    repair_llm_relationship_dicts,
    pattern_based_relationships,
)
from utilities.cti_taxonomy_loader import build_normalized_attack_patterns
from utilities.cti_linguistics import (
    normalize_behavior_text,
    canonicalize_relationship_endpoints,
    extract_dynamic_techniques
)
from utilities.cti_entity_validator import validate_entities, repair_entities

# ------------------------------------------------------------
# NLP Enhancement Layers
# ------------------------------------------------------------
from utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
from utilities.nlp.cti_relationship_recovery import clean_ir_nlp_layer2
from utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer3

# ------------------------------------------------------------
# Directory Constants
# ------------------------------------------------------------
RAW_DIR_NAME     = "raw"
CLEAN_DIR_NAME   = "clean"
OUTPUTS_IR_DIR   = "outputs_ir"
IMAGES_DIR_NAME  = "images"

# ==============================================================
# Directory Setup
# ==============================================================

def ensure_dirs(base_dir: Path):
    raw_dir    = base_dir / RAW_DIR_NAME
    clean_dir  = base_dir / CLEAN_DIR_NAME
    outputs    = base_dir / OUTPUTS_IR_DIR
    images_dir = base_dir / IMAGES_DIR_NAME
    for d in (raw_dir, clean_dir, outputs, images_dir):
        d.mkdir(parents=True, exist_ok=True)
    return raw_dir, clean_dir, outputs, images_dir

# ==============================================================
# CTI Detection
# ==============================================================

def is_likely_cti_text(txt: str) -> bool:
    lowered = txt.lower()

    cti_markers = [
        "tactic", "technique", "ttp", "exfiltrat", "lateral", "c2",
        "command and control", "malware", "ransomware", "threat actor",
        "indicator", "infrastructure", "payload", "weaponize",
        "initial access", "execution", "persistence"
    ]

    hits = sum(1 for k in cti_markers if k in lowered)
    print(f"[CTI-DETECT] len={len(txt)} keyword_hits={hits}")

    if hits >= 3:
        return True

    if len(txt) > 200 and ("attack" in lowered or "threat" in lowered):
        return True

    return False

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
    ir_dir = outputs / "debug_ir"
    mitre_dir = outputs / "debug_mitre"
    rel_dir = outputs / "debug_relationships"

    for d in (ir_dir, mitre_dir, rel_dir):
        d.mkdir(parents=True, exist_ok=True)


    for path in clean_dir.glob("*.txt"):
        print(f"\n[*] Processing: {path.name}")

        txt = path.read_text(errors="ignore")
        if not is_likely_cti_text(txt):
            print("    → Skipping: not CTI")
            continue

        debug_dir = outputs / "debug_raw_llm"
        debug_dir.mkdir(exist_ok=True)
        debug_file = debug_dir / f"{path.stem}.raw.txt"

        # ----------------------------------------------------
        # IR extraction
        # ----------------------------------------------------
        print("    → Calling LLM for IR…")
        ir = await extract_ir(txt, debug_path=debug_file)

        print(
            f"[IR] Entities → actors={len(ir.get('threat_actors',[]))} "
            f"malware={len(ir.get('malware',[]))} "
            f"tools={len(ir.get('tools',[]))} "
            f"infra={len(ir.get('infrastructure',[]))}"
        )

        # ---------------- DEBUG: IR-only ----------------
        if stop_after == "ir":
            ir_json = ir_dir / f"{path.stem}.ir-only.json"
            ir_txt  = ir_dir / f"{path.stem}.ir-only.txt"

            ir_dump = convert_sets(ir)
            ir_json.write_text(json.dumps(ir_dump, indent=2), encoding="utf-8")
            ir_txt.write_text(render_ir_summary(ir_dump), encoding="utf-8")
            print("    → Wrote IR-only JSON:", ir_json)
            print("    → Wrote IR-only TXT :", ir_txt)
            continue

        # ----------------------------------------------------
        # NLP Layers 1 & 2
        # ----------------------------------------------------
        print("    → NLP Layer 1: behavior + actor enhancements…")
        ir = clean_ir_nlp_layer1(ir, txt)

        print("    → NLP Layer 2: dependency-based relationship recovery…")
        ir = clean_ir_nlp_layer2(ir, txt)

        try:
            ir = await validate_entities(ir)
        except Exception as e:
            print(f"[!] Entity validation error: {e}")

        # ----------------------------------------------------
        # MITRE enrichment
        # ----------------------------------------------------
        print("    → Extracting MITRE techniques…")
        techniques, lookup = build_normalized_attack_patterns()

        clean_behaviors = []
        for b in ir.get("behaviors", []):
            text = b.get("text") if isinstance(b, dict) else str(b)
            text = text.strip()
            if text:
                clean_behaviors.append({"description": normalize_behavior_text(text)})

        ir["behaviors"] = clean_behaviors
        print(f"[IR] Normalized behaviors: {len(clean_behaviors)}")

        print("    → NLP Layer 3: semantic enrichment…")
        ir = clean_ir_nlp_layer3(ir, {"attack_patterns": techniques})
        layer3_ttps = ir.get("attack_patterns", [])

        ling_techs = extract_dynamic_techniques(txt, techniques)
        print(f"[LING] Extracted {len(ling_techs)} dynamic techniques")

        mitre_techs = extract_mitre_techniques(
            txt, ir.get("behaviors", []), techniques, lookup
        )

        normalized = []
        seen = set()
        for t in layer3_ttps + ling_techs + mitre_techs:
            tid = t.get("id") if isinstance(t, dict) else t
            if tid and tid not in seen:
                seen.add(tid)
                normalized.append(t if isinstance(t, dict) else {"id": tid, "name": tid})

        # ----------------------------------------------------
        # Analyst-style MITRE filtering (behavior-anchored)
        # ----------------------------------------------------
        behavior_text = " ".join(
            b.get("description","") for b in ir.get("behaviors", [])
        ).lower()

        filtered = []
        for t in normalized:
            # Normalize evidence to text for analyst filtering
            raw_evidence = t.get("evidence", "")

            if isinstance(raw_evidence, list):
                evidence_text = " ".join(str(e) for e in raw_evidence)
            else:
                evidence_text = str(raw_evidence)

            evidence = f"{evidence_text} {t.get('name','')}".lower()
            if any(word in behavior_text for word in evidence.split()):
                filtered.append(t)

        filtered.sort(key=lambda t: t.get("confidence", 0), reverse=True)
        ir["attack_patterns"] = filtered
        print(f"[IR] Total MITRE techniques after merge: {len(normalized)}")

        # ---------------- DEBUG: MITRE-only ----------------
        if stop_after == "mitre":
            mitre_json = mitre_dir / f"{path.stem}.mitre-only.json"
            mitre_txt  = mitre_dir / f"{path.stem}.mitre-only.txt"

            mitre_dump = convert_sets(ir)
            mitre_json.write_text(json.dumps(mitre_dump, indent=2), encoding="utf-8")
            mitre_txt.write_text(
                "\n".join(f"{t['id']} — {t.get('name','')}" for t in ir["attack_patterns"]),
                encoding="utf-8"
            )
            print("    → Wrote MITRE-only JSON:", mitre_json)
            print("    → Wrote MITRE-only TXT :", mitre_txt)
            continue

        # ----------------------------------------------------
        # Relationship extraction
        # ----------------------------------------------------
        print("    → Extracting relationships…")
        rel_sem = semantic_relationships(txt, ir)

        try:
            rel_llm = normalize_llm_relationships(ir.get("relationships", []), ir)
            rel_llm = repair_llm_relationship_dicts(rel_llm, ir)
        except Exception as e:
            print(f"[REL3] LLM relationship error: {e}")
            rel_llm = []

        try:
            rel_pat = pattern_based_relationships(txt, ir)
        except Exception as e:
            print(f"[REL3] Pattern-based error: {e}")
            rel_pat = []

        all_rel = canonicalize_relationship_endpoints(
            ir, ir.get("relationships", []) + rel_sem + rel_llm + rel_pat
        )

        ir["relationships"] = canonicalize_relationship_endpoints(ir, all_rel)
        ir = repair_entities(ir)
        ir["threat_actors"] = infer_threat_actors(ir)
        # valid = {
        #     e["name"].lower()
        #     for g in ("threat_actors", "malware", "tools", "infrastructure")
        #     for e in ir.get(g, [])
        # }
        valid_entities = {
            e.get("name","").lower()
            for group in ("threat_actors", "malware", "tools", "infrastructure")
            for e in ir.get(group, [])
            if e.get("name")
        }

        cleaned = [
            r for r in ir.get("relationships", [])
            if (
                r.get("source","").lower() in valid_entities
                or r.get("target","").lower() in valid_entities
            )
        ]

        ir["relationships"] = cleaned
        print(f"[REL] kept={len(cleaned)}")

        # ---------------- DEBUG: RELATIONSHIPS-only ----------------
        if stop_after == "relationships":
            rel_json = rel_dir / f"{path.stem}.relationships-only.json"
            rel_txt  = rel_dir / f"{path.stem}.relationships-only.txt"

            rel_dump = convert_sets(ir)
            rel_json.write_text(json.dumps(rel_dump, indent=2), encoding="utf-8")
            rel_txt.write_text(
                "\n".join(
                    f"{r['source']} {r['relationship']} {r['target']}"
                    for r in ir["relationships"]
                ),
                encoding="utf-8"
            )
            print("    → Wrote REL-only JSON:", rel_json)
            print("    → Wrote REL-only TXT :", rel_txt)
            continue

        # ----------------------------------------------------
        # Final outputs
        # ----------------------------------------------------
        ir = convert_sets(ir)
        final_dir = outputs / "complete"
        final_dir.mkdir(exist_ok=True)

        ir_json = final_dir / f"{path.stem}.json"
        ir_txt  = final_dir / f"{path.stem}.txt"

        ir_json.write_text(json.dumps(ir, indent=2), encoding="utf-8")
        ir_txt.write_text(render_ir_summary(ir), encoding="utf-8")

        print("    → Wrote complete JSON:", ir_json)
        print("    → Wrote complete TXT :", ir_txt)

    print("\n[+] parse-to-ir complete.")

def infer_threat_actors(ir: dict) -> list[dict]:
    """
    Infer threat actors based on demonstrated malicious agency.

    An entity is considered a threat actor if it appears as the SOURCE
    of a relationship whose TARGET is malware, tools, or infrastructure.
    This avoids brittle keyword or relationship-name filtering.
    """

    malware = {m.get("name") for m in ir.get("malware", []) if m.get("name")}
    tools = {t.get("name") for t in ir.get("tools", []) if t.get("name")}
    infrastructure = {i.get("name") for i in ir.get("infrastructure", []) if i.get("name")}

    malicious_targets = {t.lower() for t in malware | tools | infrastructure}

    malicious_sources = {
        r.get("source","").lower()
        for r in ir.get("relationships", [])
        if r.get("target","").lower() in malicious_targets
    }

    return [
        actor for actor in ir.get("threat_actors", [])
        if actor.get("name","").lower() in malicious_sources
    ]
    
def get_step_output_dir(outputs_base: Path, step: str | None) -> Path:
    """
    Return a step-scoped output directory under outputs_ir.
    """
    if not step:
        return outputs_base / "complete"

    return outputs_base / f"debug_{step}"
