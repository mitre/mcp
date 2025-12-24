#!/usr/bin/env python3
"""
Phase 2: IR → STIX 2.1 (Deterministic)
No LLM calls occur here.

Input:
    data/outputs_ir/complete_*.json  (primary)
    data/outputs_ir/*.ir-only.json   (fallback testing)

Output:
    data/outputs_stix/<stem>.stix.json
    data/outputs_stix/<stem>.stix.txt

Debug / Observability:
    data/outputs_stix/debug/<stem>.ir.json            (IR copy)
    data/outputs_stix/debug/<stem>.ir.pretty.txt      (IR pretty summary)
    data/outputs_stix/debug/<stem>.conversion.log     (step-by-step log)
    data/outputs_stix/debug/<stem>.relationships.json (relationship debug)
    data/outputs_stix/debug/<stem>.validation.txt     (validation issues)
    data/outputs_stix/debug/<stem>.metrics.json       (quality metrics)
    data/outputs_stix/debug/<stem>.audit.json         (full audit trail)
"""

import argparse
import json
from pathlib import Path
import uuid
import datetime


# ----------------- Imports from utilities -----------------
from utilities.cti_linguistics import normalize_behavior_text

from utilities.cti_stix_builders import (
    make_bundle,
    make_malware,
    make_tool,
    make_threat_actor,
    make_infrastructure,
    make_attack_pattern,
    make_observed_data,
    make_relationship,
)

from utilities.cti_taxonomy_loader import (
    load_mitre_taxonomy,
    lookup_name,
    lookup_attack_id
)

from utilities.cti_stix_validation import validate_bundle
from utilities.cti_stix_report_writer import render_stix_report
from utilities.cti_defend_enricher import enrich_stix_bundle_with_defend


# -----------------------------------------------------------
# Directories
# -----------------------------------------------------------

HERE = Path(__file__).resolve().parent
DEFAULT_BASE_DIR = HERE.parent / "data"

OUTPUTS_IR_DIR   = "outputs_ir"
OUTPUTS_STIX_DIR = "outputs_stix"
DEBUG_DIR        = "debug"
OUTPUTS_CAD_DIR  = "outputs_cad"

# -----------------------------------------------------------
# Load IR
# -----------------------------------------------------------

def load_ir(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Failed to load IR '{path.name}': {e}")
        return {}

# -----------------------------------------------------------
# Metrics + Debug helpers
# -----------------------------------------------------------

def compute_metrics(ir: dict, bundle: dict) -> dict:
    """Generate transformation quality metrics."""
    return {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "input_counts": {
            "malware": len(ir.get("malware", [])),
            "tools": len(ir.get("tools", [])),
            "threat_actors": len(ir.get("threat_actors", [])),
            "infrastructure": len(ir.get("infrastructure", [])),
            "attack_patterns": len(ir.get("attack_patterns", [])),
            "behaviors": len(ir.get("behaviors", [])),
            "relationships": len(ir.get("relationships", [])),
        },
        "output_counts": {
            "total_stix_objects": len(bundle.get("objects", [])),
            "relationships": len([
                o for o in bundle.get("objects", [])
                if o.get("type") == "relationship"
            ]),
            "attack_patterns": len([
                o for o in bundle.get("objects", [])
                if o.get("type") == "attack-pattern"
            ]),
        }
    }

def write_debug_file(path: Path, content):
    """Write either JSON or text depending on the object type."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(str(content), encoding="utf-8")

# -----------------------------------------------------------
# IR → STIX Conversion
# -----------------------------------------------------------

def convert_ir_to_stix(ir: dict, debug: dict, taxonomy: dict) -> dict:
    """
    Deterministic conversion of IR → STIX objects.
    Builds rich debug logs in the debug dictionary.
    """

    stix_objects = []
    name_to_id = {}
    debug["conversion_steps"] = []
    debug["relationship_debug"] = []

    # Helper for logging
    def log(msg):
        debug["conversion_steps"].append(msg)
    log(f"[DEBUG] Processing {len(ir.get('attack_patterns', []))} TTPs, "
    f"{len(ir.get('relationships', []))} relationships")


    # ------- Malware -------
    for m in ir.get("malware", []):
        obj = make_malware(m)
        log(f"Malware → {m.get('name')} → {obj['id'] if obj else 'SKIPPED'}")
        if obj:
            stix_objects.append(obj)
            name_to_id[obj["name"].lower()] = obj["id"]
            for alias in obj.get("aliases", []):
                name_to_id[alias.lower()] = obj["id"]


    # ------- Tools -------
    for t in ir.get("tools", []):
        obj = make_tool(t)
        log(f"Tool → {t.get('name')} → {obj['id'] if obj else 'SKIPPED'}")
        if obj:
            stix_objects.append(obj)
            name_to_id[obj["name"].lower()] = obj["id"]
            for alias in obj.get("aliases", []):
                name_to_id[alias.lower()] = obj["id"]

    # ------- Threat Actors -------
    for ta in ir.get("threat_actors", []):
        obj = make_threat_actor(ta)
        log(f"Threat Actor → {ta.get('name')} → {obj['id'] if obj else 'SKIPPED'}")
        if obj:
            stix_objects.append(obj)
            name_to_id[obj["name"].lower()] = obj["id"]
            for alias in obj.get("aliases", []):
                name_to_id[alias.lower()] = obj["id"]

    # ------- Infrastructure -------
    for inf in ir.get("infrastructure", []):
        obj = make_infrastructure(inf)
        log(f"Infrastructure → {inf.get('name')} → {obj['id'] if obj else 'SKIPPED'}")
        if obj:
            stix_objects.append(obj)
            name_to_id[obj["name"].lower()] = obj["id"]
            for alias in obj.get("aliases", []):
                name_to_id[alias.lower()] = obj["id"]

    # ------- TTPs / ATT&CK -------
    for ttp in ir.get("attack_patterns", []):
        # Stage-1 may produce:
        #   - plain strings (IR-only)
        #   - full MITRE technique dicts (MITRE-enriched)
        if isinstance(ttp, dict):
            ap_input = ttp
            label = ttp.get("id") or ttp.get("name") or str(ttp)
        else:
            ap_input = {"name": str(ttp)}
            label = str(ttp)

        obj = make_attack_pattern(ap_input, taxonomy)
        log(f"TTP → {label} → {obj['id'] if obj else 'SKIPPED'}")
        if obj:
            stix_objects.append(obj)
            name_to_id[obj["name"].lower()] = obj["id"]


    # ------- Observed Data -------
    for obs in ir.get("behaviors", []):
        if isinstance(obs, dict):
            behavior_text = obs.get("text", "")
        else:
            behavior_text = obs

        if not behavior_text:
            log(f"Observed-Data → SKIPPED (empty behavior)")
            continue
        norm = normalize_behavior_text(obs)
        obj = make_observed_data(norm)
        log(f"Observed-Data → {obj['id'] if obj else 'SKIPPED'} for {obs}")
        if obj:
            stix_objects.append(obj)

    # -------------------------------------------------------
    # Build relationships
    # -------------------------------------------------------
    for rel in ir.get("relationships", []):
        # New Stage-1 schema (primary):
        #   { "source": "...", "relationship": "...", "target": "..." }
        # Backwards-compatible fallbacks for legacy runs.

        src_name = (
            rel.get("source")
            or rel.get("src")
            or rel.get("entity1")
            or ""
        ).lower().strip()

        dst_name = (
            rel.get("target")
            or rel.get("dst")
            or rel.get("entity2")
            or ""
        ).lower().strip()

        raw_rel = (
            rel.get("relationship")
            or rel.get("rel")
            or rel.get("relation")
            or ""
        )
        
        entry = {"src": src_name, "dst": dst_name, "raw_rel": raw_rel}
        if not raw_rel:
            entry["status"] = "SKIPPED (empty verb)"
            debug["relationship_debug"].append(entry)
            continue


        if not src_name or not dst_name or not raw_rel:
            entry["status"] = "SKIPPED (missing fields)"
            debug["relationship_debug"].append(entry)
            continue

        if src_name not in name_to_id or dst_name not in name_to_id:
            entry["status"] = "SKIPPED (unresolved names)"
            debug["relationship_debug"].append(entry)
            continue

        stix_rel = normalize_relationship_verb(raw_rel)
        rel_obj = make_relationship(stix_rel, name_to_id[src_name], name_to_id[dst_name])

        if rel_obj:
            stix_objects.append(rel_obj)
            entry["status"] = f"CREATED ({rel_obj['id']})"
        else:
            entry["status"] = "SKIPPED (failed creation)"

        debug["relationship_debug"].append(entry)

    # -------------------------------------------------------
    # Final STIX Bundle
    # -------------------------------------------------------
    bundle = make_bundle(stix_objects)
    debug["bundle_id"] = bundle["id"]

    return bundle


# -----------------------------------------------------------
# Phase 2 Runner
# -----------------------------------------------------------

def run_phase2(base_dir: Path):
    outputs_ir   = base_dir / OUTPUTS_IR_DIR
    outputs_stix = base_dir / OUTPUTS_STIX_DIR
    outputs_cad  = base_dir / OUTPUTS_CAD_DIR
    debug_dir    = outputs_stix / DEBUG_DIR

    outputs_stix.mkdir(parents=True, exist_ok=True)
    outputs_cad.mkdir(parents=True, exist_ok=True)
    
    # Load MITRE taxonomy once
    taxonomy = load_mitre_taxonomy()

    print("[+] Running Phase 2: IR → STIX")

    # Prefer full Stage-1 outputs (parse-to-ir → complete_*.json)
    ir_files = sorted(outputs_ir.glob("complete_*.json"))

    # Fallback: allow IR-only outputs for testing step 1
    if not ir_files:
        ir_files = sorted(outputs_ir.glob("*.ir-only.json"))

    if not ir_files:
        print("[!] No IR files found. Run Phase 1 first.")
        return


    for ir_path in ir_files:
        print(f"    [*] Processing {ir_path.name}")

        ir = load_ir(ir_path)
        if not ir:
            print("        [!] Invalid IR, skipping.")
            continue

        stem = ir_path.stem
        debug = {}

        # Copy IR into debug
        write_debug_file(debug_dir / f"{stem}.ir.json", ir)

        # Pretty IR summary
        write_debug_file(debug_dir / f"{stem}.ir.pretty.txt",
                         json.dumps(ir, indent=2))

        # Convert IR → STIX
        bundle = convert_ir_to_stix(ir, debug, taxonomy)

        # Validate bundle
        errors = validate_bundle(bundle)
        write_debug_file(debug_dir / f"{stem}.validation.txt",
                         "\n".join(errors) if errors else "No validation issues.")

        # Track metrics
        metrics = compute_metrics(ir, bundle)
        write_debug_file(debug_dir / f"{stem}.metrics.json", metrics)

        # Write relationship debug
        write_debug_file(debug_dir / f"{stem}.relationships.json",
                         debug.get("relationship_debug", []))

        # Write conversion log
        write_debug_file(debug_dir / f"{stem}.conversion.log",
                         "\n".join(debug.get("conversion_steps", [])))

        # Write audit log
        audit = {
            "ir_file": ir_path.name,
            "bundle_id": bundle["id"],
            "metrics": metrics,
            "validation_errors": errors,
            "conversion_log": debug.get("conversion_steps", []),
            "relationship_debug": debug.get("relationship_debug", []),
        }
        audit["unresolved_entities"] = [
            r for r in debug.get("relationship_debug", [])
            if "unresolved" in r.get("status", "")
        ]

        audit["object_count_before_bundle"] = len(bundle.get("objects", []))
        audit["object_count_after_bundle"] = len(bundle.get("objects", []))


        write_debug_file(debug_dir / f"{stem}.audit.json", audit)

        # Save final STIX JSON
        stix_out = outputs_stix / f"{stem}.stix.json"
        with stix_out.open("w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)
        print(f"        → wrote {stix_out.name}")

        # Save .txt report
        report_text = render_stix_report(bundle, ir_path.name)
        (outputs_stix / f"{stem}.stix.txt").write_text(report_text, encoding="utf-8")
        print(f"        → wrote {stem}.stix.txt")

       
        # -------------------------------------------------------
        # Write CAD Graph Preview for Visualizer Testing
        # -------------------------------------------------------
        defense_root = HERE / "utilities" / "D3fend_CAD"
        enriched_bundle, ontology_info = enrich_stix_bundle_with_defend(bundle, defense_root)
        print("        → performed D3FEND enrichment")
        print("ontology_info keys:")
        print(ontology_info.keys())
        if "cad_graph" in ontology_info:
            cad_out = outputs_cad / f"{stem}.cad.json"
            with cad_out.open("w", encoding="utf-8") as f:
                json.dump(ontology_info["cad_graph"], f, indent=2)

            print(f"        → wrote {cad_out.name} (CAD Graph Preview)")
        else:
            print("        [!] No CAD graph returned from enrichment.")

        # -------------------------------------------------------
        # STDOUT PRINT: ontology modules + mappings + schema used
        # -------------------------------------------------------
        print("\n===== D3FEND ENRICHMENT DEBUG =====")

        print(f"[Ontology] Loaded {len(ontology_info['ontology_modules'])} ontology_modules:")
        for m in ontology_info["ontology_modules"]:
            print(f"   - {m}")

        print(f"\n[CAD Schema] {ontology_info['cad_schema']}")

        print("\n[Dynamic D3FEND Class Mappings]:")
        for k, v in ontology_info["mappings_used"].items():
            print(f"   {k:20s} → {v}")

        print("===== END D3FEND ENRICHMENT DEBUG =====\n")


# -----------------------------------------------------------
# STIX → CAD Enrichment Only Runner
# -----------------------------------------------------------
def run_stix_to_cad_only(base_dir: Path):
    outputs_stix = base_dir / OUTPUTS_STIX_DIR
    outputs_cad  = base_dir / OUTPUTS_CAD_DIR

    outputs_stix.mkdir(parents=True, exist_ok=True)
    outputs_cad.mkdir(parents=True, exist_ok=True)

    print("[+] Running STIX → CAD enrichment only")

    # Only process raw STIX bundles, not CAD output
    stix_files = sorted(outputs_stix.glob("*.stix.json"))
    if not stix_files:
        print("[!] No .stix.json files found in outputs_stix/.")
        return

    defense_root = HERE / "utilities" / "D3fend_CAD"

    for stix_file in stix_files:
        print(f"    [*] Enriching {stix_file.name}")

        with stix_file.open("r", encoding="utf-8") as f:
            bundle = json.load(f)
        enriched_bundle, ontology_info = enrich_stix_bundle_with_defend(bundle, defense_root)

        stem = stix_file.name.replace(".stix.json", "")
        # Write CAD graph
        if "cad_graph" in ontology_info:
            cad_out = outputs_cad / f"{stem}.cad.json"
            with cad_out.open("w", encoding="utf-8") as f:
                json.dump(ontology_info["cad_graph"], f, indent=2)
            print(f"        → wrote {cad_out.name} (CAD Graph)")
        else:
            print("        [!] No CAD graph returned.")

# -----------------------------------------------------------
# Main CLI
# -----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 2: IR → STIX")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_BASE_DIR,
        help="Base directory (contains outputs_ir/, outputs_stix/)"
    )
    
    parser.add_argument(
        "--stix-to-cad",
        action="store_true",
        help="Skip IR→STIX and ONLY run STIX→CAD enrichment"
    )

    args = parser.parse_args()
    base_dir = args.base_dir.resolve()
    print(f"[+] Using base dir: {base_dir}")
    # -------------------------------
    # Dispatch based on flag
    # -------------------------------
    if args.stix_to_cad:
        run_stix_to_cad_only(base_dir)
    else:
        run_phase2(base_dir)


if __name__ == "__main__":
    main()
