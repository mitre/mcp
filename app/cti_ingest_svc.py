#!/usr/bin/env python3
'''
Logging is preserved verbatim for debug capture via:
python3 cti_ingest_svc.py --base-dir data --step all 2>&1 | tee -a debug_mitre.log

| Step          | Description                       |
| ------------- | -------------------------------------- |
| Raw → Clean   | Normalize source material              |
| Clean → IR    | LLM extraction of entities & behaviors |
| NLP Layers    | Improve IR quality                     |
| MITRE         | Map behaviors to ATT&CK                |
| Relationships | Build entity graph                     |
| Validation    | Ensure graph correctness               |
| Outputs       | Persist IR + summary                   |
| Scenario      | (Optional) Narrative generation        |

'''

import argparse
import asyncio
import json, re
from enum import Enum
from pathlib import Path

from cti_pipeline_stage1 import (
    ensure_dirs,
    step_raw_to_clean,
    step_parse_to_ir
)

from cti_pipeline_stage2 import run_phase2




# ==============================================================
# Pipeline State
# ==============================================================

class PipelineState(Enum):
    INIT = "init"
    STAGE1 = "stage1"
    STAGE2 = "stage2"
    COMPLETE = "complete"
    FAILED = "failed"


# ==============================================================
# Service
# ==============================================================

class CTIIngestService:
    def __init__(self, on_progress=None):
        self.state = PipelineState.INIT
        self.errors = []
        self.on_progress = on_progress or (lambda *_: None)

    def _set_state(self, state: PipelineState):
        self.state = state
        self.on_progress(state.value)

    # ----------------------------------------------------------
    # Stage 1 dispatcher
    # ----------------------------------------------------------
    def run_stage1(self, base_dir: Path, step: str):
        try:
            self._set_state(PipelineState.STAGE1)

            match step:
                case "raw-to-clean":
                    step_raw_to_clean(base_dir)

                case "debug-ir":
                    asyncio.run(step_parse_to_ir(base_dir, stop_after="ir"))

                case "debug-mitre":
                    asyncio.run(step_parse_to_ir(base_dir, stop_after="mitre"))

                case "debug-relationships":
                    asyncio.run(step_parse_to_ir(base_dir, stop_after="relationships"))
                
                case "stage2":
                    self.run_stage2(base_dir)

                case "all":
                    step_raw_to_clean(base_dir)
                    asyncio.run(step_parse_to_ir(base_dir))
                    self.run_stage2(base_dir)

                case _:
                    raise ValueError(f"Unknown step: {step}")

            self._set_state(PipelineState.COMPLETE)

        except Exception:
            self.state = PipelineState.FAILED
            raise

    def run_stage2(self, base_dir: Path):
        try:
            self._set_state(PipelineState.STAGE2)
            run_phase2(base_dir)
            self._set_state(PipelineState.COMPLETE)
        except Exception as e:
            self._set_state(PipelineState.FAILED)
            self.errors.append(str(e))
            raise
    
    def status(self):
        return {
            "state": self.state.value,
            "errors": self.errors,
        }

    # # ----------------------------------------------------------
    # # Relationships-only (moved from stage file)
    # # ----------------------------------------------------------
    # async def step_relationships_only(self, base_dir: Path):
    #     raw_dir, clean_dir, outputs, _ = ensure_dirs(base_dir)

    #     debug_dir = outputs / "debug_relationships_only"
    #     debug_dir.mkdir(exist_ok=True)

    #     for ir_file in outputs.glob("*.ir-only.json"):
    #         print(f"\n[*] Relationships-only: {ir_file.name}")

    #         ir = json.loads(ir_file.read_text())

    #         txt_path = clean_dir / (ir_file.stem.replace(".ir-only", "") + ".txt")
    #         txt = txt_path.read_text(errors="ignore")

    #         rel_sem = semantic_relationships(txt, ir)

    #         try:
    #             rel_llm = normalize_llm_relationships(ir.get("relationships", []), ir)
    #         except:
    #             print(" [!] LLM relationship normalization error.")
    #             rel_llm = []

    #         try:
    #             rel_llm = repair_llm_relationship_dicts(rel_llm, ir)
    #         except:
    #             print(" [!] LLM relationship repair error.")
    #             rel_llm = []

    #         try:
    #             rel_pat = pattern_based_relationships(txt, ir)
    #         except:
    #             print(" [!] Pattern-based relationship extraction error.")
    #             rel_pat = []

    #         try:
    #             rel_llm2 = await extract_relationships_llm(ir, txt)
    #             print(f"[REL4] llm2={len(rel_llm2)}")
    #         except Exception as e:
    #             print("[REL4] LLM relationship extractor failed:", e)
    #             rel_llm2 = []

    #         all_rel = canonicalize_relationship_endpoints(
    #             ir, rel_sem + rel_llm + rel_pat + rel_llm2
    #         )

    #         valid_entities = {
    #             ent["name"].lower()
    #             for group in ("threat_actors", "malware", "tools", "infrastructure")
    #             for ent in ir.get(group, [])
    #             if ent.get("name")
    #         }

    #         filtered = [
    #             r for r in all_rel
    #             if r["source"].lower() in valid_entities
    #             and r["target"].lower() in valid_entities
    #         ]

    #         ir["relationships"] = filtered
    #         ir = convert_sets(ir)

    #         out_json = outputs / f"{txt_path.stem}.relationships-only.json"
    #         out_txt  = outputs / f"{txt_path.stem}.relationships-only.txt"

    #         out_json.write_text(json.dumps(ir, indent=2), encoding="utf-8")
    #         out_txt.write_text(
    #             "\n".join(
    #                 f"{r['source']} {r['relationship']} {r['target']}"
    #                 for r in filtered
    #             ),
    #             encoding="utf-8"
    #         )

    #         print("   → Wrote REL JSON:", out_json)
    #         print("   → Wrote REL TXT :", out_txt)

    #         debug_file = debug_dir / f"{txt_path.stem}.relationships_debug.json"
    #         debug_file.write_text(json.dumps(all_rel, indent=2), encoding="utf-8")

    # # ----------------------------------------------------------
    # # Scenario-only (raw → scenario)
    # # ----------------------------------------------------------
    # def run_scenario_only(self, base_dir: Path):
    #     raw_dir, clean_dir, outputs, images_dir = ensure_dirs(base_dir)

    #     scenario_dir = base_dir / "scenario"
    #     scenario_dir.mkdir(exist_ok=True)

    #     print("\n[*] Scenario-only mode: generating scenarios from RAW or CLEAN text")

    #     clean_exists = any(clean_dir.glob("*.txt"))
    #     if not clean_exists:
    #         print("[+] No cleaned CTI files found — running raw → clean extractor…")
    #         clean_raw_directory(base_dir, raw_dir, clean_dir, images_dir)
    #     else:
    #         print("[+] Cleaned CTI files found — skipping raw extraction.")

    #     for clean_file in clean_dir.glob("*.txt"):
    #         stem = clean_file.stem
    #         print(f"[+] Generating scenario for: {stem}")

    #         txt = clean_file.read_text(errors="ignore")
    #         if not txt.strip():
    #             print(f"[SKIP] Empty cleaned TXT for {stem}")
    #             continue

    #         placeholder_ir = {
    #             "threat_actors": [],
    #             "malware": [],
    #             "tools": [],
    #             "infrastructure": [],
    #             "behaviors": [],
    #             "attack_patterns": [],
    #             "relationships": [],
    #         }

    #         try:
    #             scenario_text = generate_attack_scenario_sync(placeholder_ir, txt)
    #         except Exception as e:
    #             print(f"[ERROR] Scenario generation failed for {stem}: {e}")
    #             continue

    #         out_path = scenario_dir / f"{stem}.raw_scenario.txt"
    #         out_path.write_text(scenario_text, encoding="utf-8")

    #         print(f"    → Wrote scenario: {out_path}")

    #     print("[+] Scenario-only complete.\n")


# ==============================================================
# CLI Entrypoint
# ==============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--step", required=True)
    args = parser.parse_args()

    print(f"[+] Base dir: {args.base_dir}")
    svc = CTIIngestService()
    svc.run_stage1(args.base_dir, args.step)


if __name__ == "__main__":
    main()
