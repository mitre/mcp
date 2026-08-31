#!/usr/bin/env python3
"""
Phase 2: IR → STIX 2.1 (Deterministic)
No LLM calls occur here.

Input:
    data/outputs_ir/complete/*.json  (primary)
    data/outputs_ir/*.ir-only.json   (fallback testing)

Output:
    data/outputs_stix/<stem>.stix.json
    data/outputs_stix/<stem>.stix.txt

Debug / Observability:
    data/outputs_stix/debug/<stem>.ir.json            (IR copy)
    data/outputs_stix/debug/<stem>.ir.pretty.txt      (IR pretty summary)
    data/outputs_stix/debug/<stem>.conversion.log     (step-by-step log)
    data/outputs_stix/debug/<stem>.validation.txt     (validation issues)
    data/outputs_stix/debug/<stem>.metrics.json       (quality metrics)
    data/outputs_stix/debug/<stem>.audit.json         (full audit trail)
"""

import json
from pathlib import Path

import datetime


# ----------------- Imports from utilities -----------------

from plugins.mcp.app.utilities.cti_stix_builders import (
    make_bundle,
    make_threat_actor,
    make_attack_pattern,
)

from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy

from plugins.mcp.app.utilities.cti_stix_validation import validate_bundle
from plugins.mcp.app.utilities.cti_stix_report_writer import render_stix_report
from plugins.mcp.app.utilities.cti_mitre_extract import hashes_to_stix_observed_data


# -----------------------------------------------------------
# Directories
# -----------------------------------------------------------

from plugins.mcp.app.utilities.paths import get_mcp_data_dir, get_mcp_root

base_dir = get_mcp_data_dir()
root_dir = get_mcp_root()

OUTPUTS_IR_DIR   = "outputs_ir/complete"
OUTPUTS_STIX_DIR = "outputs_stix"
DEBUG_DIR        = "debug"



def log(msg):
    """
    Phase-2 stdout logger.

    This ensures:
      • Messages appear in terminal
      • Messages are captured by tee debug_mitre.log
    """
    print(msg, flush=True)

# -----------------------------------------------------------
# Load IR
# -----------------------------------------------------------

def load_ir(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"[!] Failed to load IR '{path.name}': {e}")
        return {}

# -----------------------------------------------------------
# Metrics + Debug helpers
# -----------------------------------------------------------

def compute_metrics(ir: dict, bundle: dict) -> dict:
    """Generate transformation quality metrics."""
    return {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "input_counts": {
            "threat_actors": len(ir.get("threat_actors", [])),
            "attack_patterns": len(ir.get("attack_patterns", [])),
            "behaviors": len(ir.get("behaviors", [])),
            "hashes": len(ir.get("hashes", [])),
        },
        "output_counts": {
            "total_stix_objects": len(bundle.get("objects", [])),
            "attack_patterns": len([
                o for o in bundle.get("objects", [])
                if o.get("type") == "attack-pattern"
            ]),
            "threat_actors": len([
                o for o in bundle.get("objects", [])
                if o.get("type") == "threat-actor"
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
    debug["conversion_steps"] = []

    # Helper for logging
    def log(msg):
        debug["conversion_steps"].append(msg)
    log(f"[DEBUG] Processing {len(ir.get('attack_patterns', []))} TTPs")

    # ------- Threat Actors -------
    for ta in ir.get("threat_actors", []):
        obj = make_threat_actor(ta, taxonomy)
        log(f"Threat Actor → {ta.get('name')} → {obj['id'] if obj else 'SKIPPED'}")
        if obj:
            stix_objects.append(obj)

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

    # ------- Hashes (Observed Data) -------
    if ir.get("hashes"):
        hash_objects = hashes_to_stix_observed_data(ir["hashes"])
        stix_objects.extend(hash_objects)
        log(f"Observed-Data → {len(hash_objects)} file hash observables created")

    # -------------------------------------------------------
    # Final STIX Bundle
    # -------------------------------------------------------
    provenance = ir.get("provenance")
    if not provenance:
        raise ValueError("Missing provenance in IR (rerun Stage-1 to regenerate IR with provenance)")

    # provenance is built from config whether or not the model was reached, so
    # crediting it unconditionally stamped the configured model onto bundles
    # that spaCy produced end to end. Stage 1 records which extractor actually
    # ran; only the LLM path earns the attribution.
    extractor = ir.get("extractor")
    used_llm = extractor == "llm"
    model = provenance.get("model") if used_llm else None
    provider = provenance.get("provider") if used_llm else None

    bundle = make_bundle(
        stix_objects,
        model=model,
        provider=provider,
        config={**provenance, "extractor": extractor} if extractor else provenance,
    )
    debug["bundle_id"] = bundle["id"]

    return bundle

# -----------------------------------------------------------
# Phase 2 Runner
# -----------------------------------------------------------

def run_phase2(base_dir: Path):
    outputs_ir   = base_dir / OUTPUTS_IR_DIR
    outputs_stix = base_dir / OUTPUTS_STIX_DIR
    debug_dir    = outputs_stix / DEBUG_DIR

    outputs_stix.mkdir(parents=True, exist_ok=True)

    # Load MITRE taxonomy once
    taxonomy = load_mitre_taxonomy()

    log("[+] Running Phase 2: IR → STIX")

    # Prefer full Stage-1 outputs (parse-to-ir → complete_*.json)
    ir_files = sorted(outputs_ir.glob("*.json"))

    # # Fallback: allow IR-only outputs for testing step 1
    # if not ir_files:
    #     ir_files = sorted(outputs_ir.glob("*.ir-only.json"))

    if not ir_files:
        log("[!] No IR files found. Run Phase 1 first.")
        return


    for ir_path in ir_files:
        log(f"    [*] Processing {ir_path.name}")

        ir = load_ir(ir_path)
        if not ir:
            log("        [!] Invalid IR, skipping.")
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
        }
        audit["object_count"] = len(bundle.get("objects", []))

        write_debug_file(debug_dir / f"{stem}.audit.json", audit)

        # Save final STIX JSON
        stix_out = outputs_stix / f"{stem}.stix.json"
        with stix_out.open("w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)
        log(f"        → wrote {stix_out.name}")

        # Save .txt report
        report_text = render_stix_report(bundle, ir_path.name)
        (outputs_stix / f"{stem}.stix.txt").write_text(report_text, encoding="utf-8")
        log(f"        → wrote {stem}.stix.txt")





