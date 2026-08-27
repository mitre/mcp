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
import shutil
from enum import Enum
from pathlib import Path

from plugins.mcp.app.cti_pipeline_stage1 import (
    ensure_dirs,
    step_raw_to_clean,
    step_parse_to_ir
)

from plugins.mcp.app.cti_pipeline_stage2 import run_phase2

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
    def __init__(self, on_progress=None, selected=None):
        self.selected = selected or []
        self.state = PipelineState.INIT
        self.errors = []
        self.on_progress = on_progress or (lambda *_: None)

    def _set_state(self, state: PipelineState):
        self.state = state
        self.on_progress(state.value)

    # ----------------------------------------------------------
    # Stage 1 dispatcher
    # ----------------------------------------------------------
    def run_stage(self, base_dir: Path, step: str):
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

                case "all":
                    step_raw_to_clean(base_dir)
                    step_parse_to_ir(base_dir)

                    # Only run Stage 2 if IR exists
                    ir_dir = base_dir / "outputs_ir" / "complete"
                    if not ir_dir.exists() or not any(ir_dir.glob("*.json")):
                        raise RuntimeError("Stage 1 did not produce IR; aborting before Stage 2")

                    self.run_stage2(base_dir)
                    self.finalize_run(base_dir, self.selected)

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

    def finalize_run(self, base_dir: Path, selected: list[str]):
        uploads = base_dir / "raw" / "uploads"
        processed = base_dir / "raw" / "processed"

        processed.mkdir(parents=True, exist_ok=True)

        for f in uploads.iterdir():
            shutil.move(str(f), processed / f.name)

    @staticmethod
    def prepare_uploads(base_dir: Path, selected: list[str]):
        uploads = base_dir / "raw" / "uploads"
        processed = base_dir / "raw" / "processed"
        uploads.mkdir(parents=True, exist_ok=True)

        for name in selected:
            src = processed / name
            if src.exists():
                shutil.move(str(src), uploads / name)

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
    svc.run_stage(args.base_dir, args.step)

if __name__ == "__main__":
    main()
