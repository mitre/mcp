"""
cti_scenario_generator.py

Generates a human-readable attack scenario narrative derived from the final
Intermediate Representation (IR). The goal is to reconstruct:

    - The inferred event name
    - The sequence of behaviors
    - The actors involved
    - Tools / malware used
    - Infrastructure
    - Attack chain ordering (if possible)
    - A coherent story consistent with the extracted IR

This module does NOT alter the IR. It is purely analytical + generative.
"""

import json
import asyncio
from pathlib import Path

from plugins.mcp.app.utilities.llm_client import llm_generate


# --------------------------------------------------------------------
#  Scenario Prompt
# --------------------------------------------------------------------
SCENARIO_PROMPT = """
You are a cyber threat intelligence analyst. You are given an IR (Intermediate
Representation) summarizing actors, malware, tools, infrastructure, behaviors,
techniques, and relationships.

Your job is to reconstruct a chronological attack scenario:

1. Identify the threat actor(s) and motivation (if possible).
2. Describe initial access, execution, persistence, lateral movement,
   collection, exfiltration, and impact stages (only if present).
3. Reconstruct the chain of events using the behaviors.
4. Respect any relationships (actor → malware, malware → infrastructure, etc.)
5. If timestamps are missing, infer a reasonable timeline order from behaviors.
6. Produce a concise but complete narrative (300–600 words).
7. Use correct cyber-defense terminology.
8. Include any inferred gaps.

Your output MUST be in plain text with no lists or bullets — a coherent story.
"""


# ========================================================================
#  ASYNC SCENARIO GENERATOR (THE REAL WORKER)
# ========================================================================
async def generate_attack_scenario_async(ir: dict, raw_text: str) -> str:
    payload = {
        "report_text": raw_text,
        "ir": ir
    }

    prompt = (
        SCENARIO_PROMPT
        + "\n\n--- DATA START ---\n"
        + json.dumps(payload, indent=2)
        + "\n--- DATA END ---\n"
    )

    response = await llm_generate(prompt, profile="cti")

    if not response:
        return "[ERROR] Scenario LLM returned empty response."

    return response.strip()


# ========================================================================
#  SYNC WRAPPER — SAFE TO USE OUTSIDE OF ANY EVENT LOOP
# ========================================================================
def generate_attack_scenario_sync(ir: dict, raw_text: str) -> str:
    """
    Used ONLY in scenario-only mode.
    It is safe because this mode runs outside asyncio.
    """
    return asyncio.run(generate_attack_scenario_async(ir, raw_text))


# ========================================================================
#  UNIVERSAL WRAPPER — WORKS IN BOTH ASYNC AND SYNC CONTEXTS
# ========================================================================
async def generate_attack_scenario(ir: dict, raw_text: str):
    """
    Safe to call inside the main pipeline (which already runs inside asyncio).
    """
    return await generate_attack_scenario_async(ir, raw_text)


# ========================================================================
#  SAVE FUNCTION
# ========================================================================
def save_scenario(text: str, scenario_dir: Path, stem: str) -> Path:
    scenario_dir.mkdir(parents=True, exist_ok=True)
    out_path = scenario_dir / f"{stem}.scenario.txt"
    out_path.write_text(text, encoding="utf-8")
    return out_path
