#!/usr/bin/env python3
"""
Phase 1 — CTI → Intermediate Representation (IR)

This orchestrator performs:

    1. raw → clean text
    2. clean → IR (via LLM)
    3. MITRE technique enrichment
    4. Relationship extraction
    5. Entity canonicalization
    6. Output IR JSON + human readable summary

All extraction logic lives in utilities modules:
    - cti_parsing_test.py       (LLM → IR)
    - cti_mitre_extract.py      (MITRE ATT&CK enrichment)
    - cti_relationships.py      (semantic + LLM relationship parsing)
    - cti_linguistics.py        (normalization + canonicalization)

No logic duplication belongs in this file.
"""

import argparse
import json
from pathlib import Path
import subprocess
import re
import trafilatura
from bs4 import BeautifulSoup
import asyncio

# ------------------------------------------------------------
# IMPORT CLEAN MODULES
# ------------------------------------------------------------

# ------------------------------------------------------------
# CTI Raw Text Cleaning and Extraction
# ------------------------------------------------------------
from utilities.cti_raw_parser import parse_raw_cti
from utilities.cti_raw_cleaner import clean_raw_directory


from cti_parsing_test import extract_ir, render_ir_summary, extract_relationships_llm
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
    canonicalize_relationship_endpoints
)
from utilities.cti_entity_validator import validate_entities, repair_entities
from utilities.cti_linguistics import extract_dynamic_techniques

# ------------------------------------------------------------
# NLP Enhancement Layers
# ------------------------------------------------------------
from utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
from utilities.nlp.cti_relationship_recovery import clean_ir_nlp_layer2
from utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer3

# ------------------------------------------------------------
# CTI Scenario Generation
# ------------------------------------------------------------
from utilities.cti_scenario_generator import (
    generate_attack_scenario,      # async (pipeline)
    generate_attack_scenario_sync, # sync (scenario-only)
    save_scenario
)

# ==============================================================  
# Directory Setup
# ==============================================================  

HERE = Path(__file__).resolve().parent
DEFAULT_BASE_DIR = HERE.parent / "data"

RAW_DIR_NAME     = "raw"
CLEAN_DIR_NAME   = "clean"
OUTPUTS_IR_DIR   = "outputs_ir"
IMAGES_DIR_NAME  = "images"
PHASE1_ONLY = True

def ensure_dirs(base_dir: Path):
    raw_dir    = base_dir / RAW_DIR_NAME
    clean_dir  = base_dir / CLEAN_DIR_NAME
    outputs    = base_dir / OUTPUTS_IR_DIR
    images_dir = base_dir / IMAGES_DIR_NAME
    for d in (raw_dir, clean_dir, outputs, images_dir):
        d.mkdir(parents=True, exist_ok=True)
    return raw_dir, clean_dir, outputs, images_dir

# ==============================================================  
# Text Extraction (raw → clean)
# ==============================================================  

def is_likely_cti_text(txt: str) -> bool:
    """
    More robust CTI detection:
    - Allow shorter reports
    - Allow high symbol/number ratio (IoCs)
    - Validate based on CTI keywords
    """

    lowered = txt.lower()

    cti_markers = [
        "tactic", "technique", "ttp", "exfiltrat", "lateral", "c2",
        "command and control", "malware", "ransomware", "threat actor",
        "indicator", "infrastructure", "payload", "weaponize",
        "initial access", "execution", "persistence"
    ]

    hits = sum(1 for k in cti_markers if k in lowered)

    # Debug
    print(f"[CTI-DETECT] len={len(txt)} keyword_hits={hits}")

    # If >3 CTI markers are found → CTI
    if hits >= 3:
        return True

    # If short but strongly structured → likely CTI
    if len(txt) > 200 and ("attack" in lowered or "threat" in lowered):
        return True

    return False

def step_raw_to_clean(base_dir: Path):
    raw_dir, clean_dir, _, images_dir = ensure_dirs(base_dir)
    clean_raw_directory(base_dir, raw_dir, clean_dir, images_dir)

# ==============================================================  
# Step 2 — clean → IR - ALL
# ==============================================================  

async def step_parse_to_ir(base_dir: Path):
    _, clean_dir, outputs, _ = ensure_dirs(base_dir)

    for path in clean_dir.glob("*.txt"):
        print(f"\n[*] Processing: {path.name}")

        txt = path.read_text(errors="ignore")
        if not is_likely_cti_text(txt):
            print("    → Skipping: not CTI")
            continue

        # DEBUG capture LLM raw output
        debug_dir = outputs / "debug_raw_llm"
        debug_dir.mkdir(exist_ok=True)
        debug_file = debug_dir / f"{path.stem}.raw.txt"

        # ----------------------------------------------------
        # LLM IR extraction
        # ----------------------------------------------------

        print("    → Calling LLM for IR…")
        STRICT_ENTITIES_PROMPT = """
            Extract CTI entities realistically, not overly strict.

            THREAT ACTORS:
            - Named adversaries or ransomware groups.
            - Examples: BlackMatter, LockBit, FIN7, APT29.
            - Must never be analysts or vendors.

            MALWARE:
            - Malware families and payloads (e.g., Exmatter).

            TOOLS:
            - Software, utilities, post-exploitation frameworks.

            INFRASTRUCTURE:
            - C2 servers, hosting, botnets, IPs, URLs.

            BEHAVIORS:
            - Short descriptions of malicious actions (< 12 words).

            RELATIONSHIPS:
            - Prefer canonical verbs: uses, deploys, executes, loads,
            communicates-with, associated-with, exfiltrates.
            - If unsure, extract anyway — do NOT skip.

            Output JSON only.
            Never return full sentences as names.
            Never include descriptions inside "name".
            """
        llm_input = STRICT_ENTITIES_PROMPT + "\n\nCTI REPORT:\n" + txt
        ir = await extract_ir(txt, debug_path=debug_file)
        print(f"[IR] Entities → actors={len(ir.get('threat_actors',[]))} "
            f"malware={len(ir.get('malware',[]))} "
            f"tools={len(ir.get('tools',[]))} "
            f"infra={len(ir.get('infrastructure',[]))}")

        # ----------------------------------------------------
        # NLP Layer 1 — behavior expansion & actor normalization
        # ----------------------------------------------------
        
        print("    → NLP Layer 1: behavior + actor enhancements…")
        ir = clean_ir_nlp_layer1(ir, txt)
        
        # ----------------------------------------------------
        # NLP Layer 2 — relationship recovery from dependency parse
        # ----------------------------------------------------
        print("    → NLP Layer 2: dependency-based relationship recovery…")
        ir = clean_ir_nlp_layer2(ir, txt)
        
        # LLM sanity-check of entities (double check)
        try:
            ir = await validate_entities(ir)
        except Exception as e:
            print(f"[!] Entity validation error: {e}")
        # ----------------------------------------------------
        # MITRE technique enrichment
        # ----------------------------------------------------

        print("    → Extracting MITRE techniques…")
        techniques, lookup = build_normalized_attack_patterns()
        # Behaviors may be strings, dicts, or NLP-expanded dicts
        clean_behaviors = []
        for b in ir.get("behaviors", []):
            if isinstance(b, dict):
                text = b.get("text") or b.get("description") or ""
                text = text.strip()
                if text:
                    clean_behaviors.append({"description": normalize_behavior_text(text)})
            else:
                clean_behaviors.append({"description": str(b).strip()})

        clean_behaviors = [b for b in clean_behaviors if b["description"].strip()]
        ir["behaviors"] = clean_behaviors

        ir["behaviors"] = clean_behaviors
        print(f"[IR] Normalized behaviors: {len(clean_behaviors)}")
        for b in ir["behaviors"]:
            desc = b["description"]
            b["text"] = desc
        behavior_tokens = set()

        for b in ir.get("behaviors", []):
            if isinstance(b, dict):
                tokens = re.findall(r"[a-z0-9]+", b.get("description","").lower())
                behavior_tokens.update(tokens)
            else:
                behavior_tokens.update(str(b).lower().split())
        
        # ---------------------------------------------
        # NLP Layer 3 — semantic enrichment
        # ---------------------------------------------
        print("    → NLP Layer 3: semantic enrichment (vectors + kill-chain)…")
        ir = clean_ir_nlp_layer3(ir, {"attack_patterns": techniques})
        layer3_ttps = ir.get("attack_patterns", [])

        # ---------------------------------------------
        # Dynamic techniques from linguistic analysis
        # ---------------------------------------------
        ling_techs = extract_dynamic_techniques(txt, techniques)
        print(f"[LING] Extracted {len(ling_techs)} dynamic techniques")
        for lt in ling_techs:
            print(f"   → {lt['id']}  score={lt['confidence']}  phrase='{lt['evidence']}'")

        # ---------------------------------------------
        # MITRE extraction
        # ---------------------------------------------
        mitre_techs = extract_mitre_techniques(
            txt,
            ir.get("behaviors", []),
            techniques,
            lookup
        )

        # ---------------------------------------------
        # Normalize, merge, dedupe
        # ---------------------------------------------
        normalized_ttp_list = []

        # normalize any strings → TTP dicts
        for t in layer3_ttps + ling_techs + mitre_techs:
            if isinstance(t, str):
                normalized_ttp_list.append({"id": t.strip(), "name": t.strip()})
            elif isinstance(t, dict):
                normalized_ttp_list.append(t)

        # final dedupe
        final = []
        seen = set()
        for t in normalized_ttp_list:
            tid = t.get("id")
            if tid and tid not in seen:
                seen.add(tid)
                final.append(t)

        ir["attack_patterns"] = final
        print(f"[IR] Total MITRE techniques after merge: {len(ir['attack_patterns'])}")

        # ----------------------------------------------------
        # Relationship extraction
        # ----------------------------------------------------

        print("    → Extracting relationships…")
        rel_sem = semantic_relationships(txt, ir)
        print(f"[REL3] semantic_relationships → {len(rel_sem)} candidates")

        try:
            rel_llm = normalize_llm_relationships(ir.get("relationships", []), ir)
        except Exception as e:
            print(f"[REL3] LLM relationship normalization error: {e}")
            rel_llm = []

        try:
            rel_llm = repair_llm_relationship_dicts(rel_llm, ir)
        except Exception as e:
            print(f"[REL3] LLM relationship repair error: {e}")
            rel_llm = []

        try:
            rel_pat = pattern_based_relationships(txt, ir)
        except Exception as e:
            print(f"[REL3] Pattern-based relationship extraction error: {e}")
            rel_pat = []

        print(
            f"[REL3] semantic={len(rel_sem)} "
            f"llm={len(rel_llm)} "
            f"pattern={len(rel_pat)}"
        )
        layer2_relationships = ir.get("relationships", [])
        all_rel = canonicalize_relationship_endpoints(
            ir, layer2_relationships + rel_sem + rel_llm + rel_pat
        )
        print(f"[REL3] all_rel after canonicalization: {len(all_rel)}")

        # Merge and canonicalize
        ir["relationships"] = canonicalize_relationship_endpoints(ir, all_rel)             
        ir = repair_entities(ir)
        # ---------------------------------------------------------
        # Removes relationships where neither endpoint is a valid entity
        # Uses dynamic taxonomies
        # ---------------------------------------------------------

        # -----------------------------------------------
        # Fuzzy entity resolution for relationship cleanup
        # -----------------------------------------------

        def clean_ent(n):
            n = n.lower()
            n = re.sub(r"[^a-z0-9 ]", "", n)
            return n.strip()

        # Build canonical + alias sets
        expanded_entities = set()

        for group in ("threat_actors", "malware", "tools", "infrastructure"):
            for ent in ir.get(group, []):
                name = ent.get("name", "")
                if name:
                    expanded_entities.add(clean_ent(name))
                for alias in ent.get("aliases", []):
                    expanded_entities.add(clean_ent(alias))

        cleaned = []
        valid = {e["name"].lower() for g in ("threat_actors","malware","tools","infrastructure")
                for e in ir.get(g,[])}

        for rel in ir.get("relationships", []):
            if rel.get("source","").lower() in valid and rel.get("target","").lower() in valid:
                cleaned.append(rel)

        ir["relationships"] = cleaned
        print(f"[REL] kept={len(cleaned)}")

        # ----------------------------------------------------
        # Save IR outputs
        # ----------------------------------------------------

        ir_json = outputs / f"complete_{path.stem}.json"
        ir_txt  = outputs / f"complete_{path.stem}.txt"
        ir = convert_sets(ir)

        ir_json.write_text(json.dumps(ir, indent=2), encoding="utf-8")
        ir_txt.write_text(render_ir_summary(ir), encoding="utf-8")

        print("    → Wrote complete JSON:", ir_json)
        print("    → Wrote complete TXT :", ir_txt)

        # ----------------------------------------------------
        # Attack Scenario Generation
        # ----------------------------------------------------
        print("    → Generating scenario narrative…")

        scenario_dir = base_dir / "scenario"
        scenario_text = await generate_attack_scenario(ir, txt)
        scenario_path = save_scenario(scenario_text, scenario_dir, path.stem)

        print("    → Wrote scenario narrative:", scenario_path)
        
    print("\n[+] parse-to-ir complete.")

# ==============================================================  
# Main Entrypoint
# ==============================================================  

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--step", choices=[
        "raw-to-clean",
        "ir-only",
        "mitre-only",
        "relationships-only",
        "scenario-only",
        "all"
    ], default="all")

    args = parser.parse_args()

    print(f"[+] Base dir: {args.base_dir}")
    # FULL pipeline
    if args.step == "all":
        print("[ALL] Step 1: raw → clean")
        step_raw_to_clean(args.base_dir)

        print("[ALL] Step 2: clean → IR (LLM extraction only)")
        asyncio.run(step_ir_only(args.base_dir))

        print("[ALL] Step 3: MITRE enrichment")
        step_mitre_only(args.base_dir)

        print("[ALL] Step 4: relationship extraction")
        asyncio.run(step_relationships_only(args.base_dir))
        return
    
    # INDIVIDUAL STEPS
    if args.step == "raw-to-clean":
        step_raw_to_clean(args.base_dir)
        return
    
    if args.step == "ir-only":
        asyncio.run(step_ir_only(args.base_dir))
        return

    if args.step == "mitre-only":
        step_mitre_only(args.base_dir)
        return

    if args.step == "relationships-only":
        asyncio.run(step_relationships_only(args.base_dir))
        return
    
    if args.step == "scenario-only":
        run_scenario_only(args.base_dir)
        return

    

# ==============================================================
# Sub-steps for testing each step of the pipeline for Stage 1
# ==============================================================

async def step_ir_only(base_dir: Path):
    raw_dir, clean_dir, outputs, _ = ensure_dirs(base_dir)

    debug_dir = outputs / "debug_ir_only"
    debug_dir.mkdir(exist_ok=True)

    for path in clean_dir.glob("*.txt"):
        print(f"\n[*] IR-only: {path.name}")

        txt = path.read_text(errors="ignore")
        if not is_likely_cti_text(txt):
            print("   → Skipping: not CTI")
            continue

        # Raw LLM output snapshot
        raw_llm_file = debug_dir / f"{path.stem}.raw_llm.txt"

        # ----------------------------------------------------
        # PURE IR extraction (NO validation, NO enrichment)
        # ----------------------------------------------------
        ir = await extract_ir(txt, debug_path=raw_llm_file)

        # ----------------------------------------------------
        # Write IR-only outputs
        # ----------------------------------------------------
        out_json = outputs / f"{path.stem}.ir-only.json"
        out_txt  = outputs / f"{path.stem}.ir-only.txt"
        ir = convert_sets(ir)
        out_json.write_text(json.dumps(ir, indent=2), encoding="utf-8")
        out_txt.write_text(render_ir_summary(ir), encoding="utf-8")

        print("   → Wrote IR JSON:", out_json)
        print("   → Wrote IR TXT :", out_txt)

def step_mitre_only(base_dir: Path):
    raw_dir, clean_dir, outputs, _ = ensure_dirs(base_dir)

    debug_dir = outputs / "debug_mitre_only"
    debug_dir.mkdir(exist_ok=True)

    try:
        techniques, lookup = build_normalized_attack_patterns()
    except FileNotFoundError as e:
        print("[!] Missing MITRE dataset:", e)
        return

    for ir_file in outputs.glob("*.ir-only.json"):
        print(f"\n[*] MITRE-only: {ir_file.name}")

        ir = json.loads(ir_file.read_text())

        txt_path = clean_dir / (ir_file.stem.replace(".ir-only", "") + ".txt")
        txt = txt_path.read_text(errors="ignore")

        # Extract MITRE techniques
        mitre = extract_mitre_techniques(txt, ir.get("behaviors", []), techniques, lookup)
        ir["attack_patterns"] = mitre
        ir = convert_sets(ir)

        # -------------------------------
        # Write MITRE-only outputs
        # -------------------------------
        out_json = outputs / f"{txt_path.stem}.mitre-only.json"
        out_txt  = outputs / f"{txt_path.stem}.mitre-only.txt"

        out_json.write_text(json.dumps(ir, indent=2), encoding="utf-8")
        out_txt.write_text("\n".join(f"{t['id']} — {t['name']}" for t in mitre),
                           encoding="utf-8")

        print("   → Wrote MITRE JSON:", out_json)
        print("   → Wrote MITRE TXT :", out_txt)

        # Debug dump
        debug_file = debug_dir / f"{txt_path.stem}.mitre_debug.json"
        debug_file.write_text(json.dumps(convert_sets(mitre), indent=2), encoding="utf-8")

async def step_relationships_only(base_dir: Path):
    raw_dir, clean_dir, outputs, _ = ensure_dirs(base_dir)

    debug_dir = outputs / "debug_relationships_only"
    debug_dir.mkdir(exist_ok=True)

    for ir_file in outputs.glob("*.ir-only.json"):
        print(f"\n[*] Relationships-only: {ir_file.name}")

        ir = json.loads(ir_file.read_text())

        txt_path = clean_dir / (ir_file.stem.replace(".ir-only", "") + ".txt")
        txt = txt_path.read_text(errors="ignore")

        # ------------------------------
        # Run full relationship pipeline
        # ------------------------------
        rel_sem = semantic_relationships(txt, ir)
        try:
            rel_llm = normalize_llm_relationships(ir.get("relationships", []), ir)
        except:
            print(" [!] LLM relationship normalization error.")
            rel_llm = []
        try:
            rel_llm = repair_llm_relationship_dicts(rel_llm, ir)
        except:
            print(" [!] LLM relationship repair error.")
            rel_llm = []
        try:
            rel_pat = pattern_based_relationships(txt, ir)
        except:
            print(" [!] Pattern-based relationship extraction error.")
            rel_pat = []
        
        try:
            rel_llm2 = await extract_relationships_llm(ir, txt)
            print(f"[REL4] llm2={len(rel_llm2)}")
        except Exception as e:
            print("[REL4] LLM relationship extractor failed:", e)
            rel_llm2 = []

        all_rel = canonicalize_relationship_endpoints(
            ir, rel_sem + rel_llm + rel_pat + rel_llm2
        )

        # Filter invalid
        valid_entities = {
            ent["name"].lower()
            for group in ("threat_actors", "malware", "tools", "infrastructure")
            for ent in ir.get(group, [])
            if ent.get("name")
        }

        filtered = [
            r for r in all_rel
            if r["source"].lower() in valid_entities and r["target"].lower() in valid_entities
        ]

        ir["relationships"] = filtered
        ir = convert_sets(ir)

        # ------------------------------
        # Write outputs
        # ------------------------------
        out_json = outputs / f"{txt_path.stem}.relationships-only.json"
        out_txt  = outputs / f"{txt_path.stem}.relationships-only.txt"

        out_json.write_text(json.dumps(ir, indent=2), encoding="utf-8")
        out_txt.write_text(
            "\n".join(f"{r['source']} {r['relationship']} {r['target']}"
                      for r in filtered),
            encoding="utf-8"
        )

        print("   → Wrote REL JSON:", out_json)
        print("   → Wrote REL TXT :", out_txt)

        # Raw debug
        debug_file = debug_dir / f"{txt_path.stem}.relationships_debug.json"
        debug_file.write_text(json.dumps(all_rel, indent=2), encoding="utf-8")

def run_scenario_only(base_dir: Path):
    raw_dir, clean_dir, outputs, images_dir = ensure_dirs(base_dir)

    scenario_dir = base_dir / "scenario"
    scenario_dir.mkdir(exist_ok=True)

    print("\n[*] Scenario-only mode: generating scenarios from RAW or CLEAN text")

    # ------------------------------------------------------------
    # Ensure clean text exists — if not, create it from raw
    # ------------------------------------------------------------
    clean_exists = any(clean_dir.glob("*.txt"))
    if not clean_exists:
        print("[+] No cleaned CTI files found — running raw → clean extractor…")
        clean_raw_directory(base_dir, raw_dir, clean_dir, images_dir)
    else:
        print("[+] Cleaned CTI files found — skipping raw extraction.")

    # ------------------------------------------------------------
    # Use every cleaned TXT to generate a scenario
    # ------------------------------------------------------------
    for clean_file in clean_dir.glob("*.txt"):
        stem = clean_file.stem
        print(f"[+] Generating scenario for: {stem}")

        # Read cleaned text
        txt = clean_file.read_text(errors="ignore")
        if not txt.strip():
            print(f"[SKIP] Empty cleaned TXT for {stem}")
            continue
        # --------------------------------------------------------
        # Minimal IR placeholder so generator has structure
        # --------------------------------------------------------
        placeholder_ir = {
            "threat_actors": [],
            "malware": [],
            "tools": [],
            "infrastructure": [],
            "behaviors": [],
            "attack_patterns": [],
            "relationships": []
        }
        
        # --------------------------------------------
        # Scenario generation — NO IR needed here
        # This is raw → scenario inference
        # --------------------------------------------
        try:
            scenario_text = generate_attack_scenario_sync(placeholder_ir, txt)
        except Exception as e:
            print(f"[ERROR] Scenario generation failed for {stem}: {e}")
            continue

        # --------------------------------------------
        # Save scenario
        # --------------------------------------------
        out_path = scenario_dir / f"{stem}.raw_scenario.txt"
        out_path.write_text(scenario_text, encoding="utf-8")

        print(f"    → Wrote scenario: {out_path}")

    print("[+] Scenario-only complete.\n")

if __name__ == "__main__":
    main()
