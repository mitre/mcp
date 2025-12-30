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
from cti_pipeline_stage3 import run_phase3_infrastructure

# ==============================================================
# Pipeline State
# ==============================================================

class PipelineState(Enum):
    INIT = "init"
    STAGE1 = "stage1"
    STAGE2 = "stage2"
    STAGE3 = "stage3"
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
                    step_parse_to_ir(base_dir, stop_after="ir")

                case "debug-mitre":
                    step_parse_to_ir(base_dir, stop_after="mitre")

                case "debug-relationships":
                    step_parse_to_ir(base_dir, stop_after="relationships")
                
                case "stage2":
                    self.run_stage2(base_dir)
                
                case "stage3-infra":
                    # default deterministic
                    self.run_stage3(base_dir, use_llm=False)
                
                case "stage3-infra-llm":
                    # optional: use LLM for refinement only
                    self.run_stage3(base_dir, use_llm=True)

                case "all":
                    step_raw_to_clean(base_dir)
                    step_parse_to_ir(base_dir)
                    self.run_stage2(base_dir)
                    # self.run_stage3(base_dir, use_llm=False)

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
        
    def run_stage3(self, base_dir: Path, use_llm: bool = False):
        try:
            self._set_state(PipelineState.STAGE3)
            run_phase3_infrastructure(base_dir, use_llm=use_llm)
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
