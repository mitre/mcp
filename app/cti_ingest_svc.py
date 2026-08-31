#!/usr/bin/env python3
'''
Logging is preserved verbatim for debug capture via:
python3 cti_ingest_svc.py --base-dir data --step all 2>&1 | tee -a debug_mitre.log

| Step         | Description                                    |
| ------------ | ---------------------------------------------- |
| raw-to-clean | Normalize source material                      |
| debug-ir     | Stop after IR extraction                       |
| stage2       | IR -> STIX bundle only                         |
| all          | Everything, in order                           |

'''

import argparse
import shutil
from enum import Enum
from pathlib import Path

from plugins.mcp.app.cti_pipeline_stage1 import (
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
                    step_parse_to_ir(base_dir, stop_after="ir", only=self.selected)

                case "stage2":
                    self.run_stage2(base_dir)

                case "all":
                    step_raw_to_clean(base_dir)
                    step_parse_to_ir(base_dir, only=self.selected)

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
        """Retire the reports this run actually processed.

        This moved everything in uploads/ and never read its own argument, so
        a report the operator did not select was retired having never been
        cleaned or extracted. list_cti_raw stamps a literal "processed" on
        that directory, so it then rendered green.

        An empty selection still means everything, matching the convention
        step_parse_to_ir uses for the same reason.
        """
        uploads = base_dir / "raw" / "uploads"
        processed = base_dir / "raw" / "processed"

        processed.mkdir(parents=True, exist_ok=True)

        names = set(selected or [])
        for f in uploads.iterdir():
            if names and f.name not in names:
                continue
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
