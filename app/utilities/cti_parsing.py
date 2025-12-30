"""
cti_parsing_test.py — Phase 1 IR Extraction Engine

This module:
    • Calls the LLM
    • Produces a clean Intermediate Representation (IR)
    • Repairs malformed JSON
    • Normalizes missing fields
    • NO MITRE extraction
    • NO relationships extraction
    • NO canonicalization
"""

import json
import re
from pathlib import Path
import httpx

API_BASE = "http://127.0.0.1:11434"
MODEL_NAME = "gemma3n:latest"

# Give the repair engine more chances
MAX_REPAIR_ATTEMPTS = 3

# ---------------------------------------------------------
# LLM CALL (with strong determinism + error handling)
# ---------------------------------------------------------

async def ollama_generate_async(prompt: str) -> str:
    print("[LLM] Generating IR...")
    print(prompt)
    async with httpx.AsyncClient(timeout=300) as client:
        try:
            resp = await client.post(
                f"{API_BASE}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "top_p": 1.0,
                        "repeat_penalty": 1.0
                    }
                }
            )
        except Exception as e:
            print(f"[LLM][ERROR] {e}")
            return ""

        return resp.json().get("response", "")

# ---------------------------------------------------------
# Prompt builder — deterministic schema
# ---------------------------------------------------------

def build_ir_prompt(cti_text: str) -> str:
    return f"""
        You are a senior cyber threat intelligence analyst.

        Extract ONLY the following structured CTI fields into ONE JSON object:

        {{
        "threat_actors": [
            {{"name": "", "description": ""}}
        ],
        "malware": [
            {{"name": "", "description": ""}}
        ],
        "tools": [
            {{"name": "", "description": ""}}
        ],
        "infrastructure": [
            {{"name": "", "description": ""}}
        ],
        "attack_patterns": [],
        "behaviors": [
            {{"description": ""}}
        ],
        "relationships": [
            {{"source": "", "relationship": "", "target": ""}}
        ]
        }}

        STRICT RULES:
        - ALWAYS return valid JSON
        - ALWAYS fill descriptions when possible
        - NEVER invent entities
        - NEVER echo CTI text
        - NEVER add additional keys
        - ALWAYS use lists (even if empty)
        - Relationship verbs MUST be short actions like:
        ["uses", "deploys", "exploits", "targets", "communicates-with", "associated-with"]

        CTI REPORT:
        \"\"\"{cti_text}\"\"\"
        """.strip()

# ---------------------------------------------------------
# JSON cleaning + aggressive repair
# ---------------------------------------------------------

def clean_raw_to_json(raw: str):
    raw = raw.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    # First attempt — raw JSON as-is
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Second pass — extract the largest JSON-looking block
    m = re.search(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}", raw)
    if m:
        block = m.group(0)
        try:
            return json.loads(block)
        except Exception:
            pass

    # Third pass — aggressive wrap fix  
    try:
        cleaned = raw.strip()
        if cleaned.count("{") == 1 and cleaned.count("}") == 0:
            cleaned = cleaned + "}"
        return json.loads(cleaned)
    except Exception:
        pass

    return None

# ---------------------------------------------------------
# Schema enforcement — corrected version
# ---------------------------------------------------------

def enforce_ir_schema(ir: dict) -> dict:
    fields = [
        "threat_actors", "malware", "tools",
        "infrastructure", "attack_patterns",
        "behaviors", "relationships"
    ]

    clean = {}

    for f in fields:
        v = ir.get(f)

        # Missing field → empty list
        if v is None:
            clean[f] = []
            continue

        # List → keep but clean invalid entries
        if isinstance(v, list):
            filtered = []
            for item in v:
                if isinstance(item, dict):
                    # Ensure minimal validity
                    if f == "behaviors":
                        if "description" in item:
                            filtered.append(item)
                    elif f == "attack_patterns":
                        # should be empty list anyway
                        filtered.append(item)
                    else:
                        if "name" in item:
                            filtered.append(item)
                elif isinstance(item, str):
                    if item.strip():
                        filtered.append(item.strip())
            clean[f] = filtered
            continue

        # Dict → wrap into list
        if isinstance(v, dict):
            if f == "behaviors" and "description" in v:
                clean[f] = [v]
            elif "name" in v or "description" in v:
                clean[f] = [v]
            else:
                clean[f] = []
            continue

        # String → wrap
        if isinstance(v, str):
            if v.strip():
                clean[f] = [v.strip()]
            else:
                clean[f] = []
            continue

        clean[f] = []

    return clean

# ---------------------------------------------------------
# Main IR extractor
# ---------------------------------------------------------

async def extract_ir(cti_text: str, debug_path: Path = None) -> dict:
    prompt = build_ir_prompt(cti_text)
    raw = await ollama_generate_async(prompt)

    if debug_path:
        with debug_path.open("a", encoding="utf-8") as f:
            f.write(raw + "\n")

    orig_raw = raw
    ir = clean_raw_to_json(raw)

    # If valid → enforce schema and return
    if ir is not None:
        return enforce_ir_schema(ir)

    # Empty or invalid JSON
    print("[LLM][WARN] Empty or malformed IR returned, attempting repair…")

    # Log original bad JSON
    debug_log_path = Path("debug_mitre.log")
    with debug_log_path.open("a", encoding="utf-8") as dbg:
        dbg.write("\n\n========== FIRST BAD LLM OUTPUT ==========\n")
        dbg.write(orig_raw)
        dbg.write("\n==========================================\n")

    # Repair attempts
    for i in range(MAX_REPAIR_ATTEMPTS):
        print(f"[LLM][REPAIR] Attempt {i+1}/{MAX_REPAIR_ATTEMPTS}")

        repair_prompt = f"""
        Your previous output was invalid JSON.

        FIX ONLY THE JSON SYNTAX.
        DO NOT modify values.
        DO NOT add or remove fields.

        Return EXACTLY ONE valid JSON object matching this schema:

        {{
        "threat_actors": [],
        "malware": [],
        "tools": [],
        "infrastructure": [],
        "attack_patterns": [],
        "behaviors": [],
        "relationships": []
        }}

        Bad JSON:
        \"\"\"{orig_raw}\"\"\"
        """
        raw = await ollama_generate_async(repair_prompt)
        ir = clean_raw_to_json(raw)

        if ir is not None:
            return enforce_ir_schema(ir)

    # Total failure → return empty schema
    return enforce_ir_schema({})

# ---------------------------------------------------------
# Summary (for human-readable debug)
# ---------------------------------------------------------

def render_ir_summary(ir: dict) -> str:
    lines = []

    def section(title, items):
        lines.append(f"{title}:")
        if not items:
            lines.append("  (none)")
        else:
            for it in items:
                if isinstance(it, dict):
                    if "description" in it or "text" in it:
                        btxt = it.get("description") or it.get("text") or ""
                        lines.append(f"  - {btxt}")
                    else:
                        name = it.get("name", "(unnamed)")
                        desc = it.get("description", "")
                        lines.append(f"  - {name}: {desc}")
        lines.append("")

    section("Threat Actors", ir.get("threat_actors", []))
    section("Malware", ir.get("malware", []))
    section("Tools", ir.get("tools", []))
    section("Infrastructure", ir.get("infrastructure", []))
    section("Attack Patterns", ir.get("attack_patterns", []))
    section("Behaviors", ir.get("behaviors", []))
    section("Relationships", ir.get("relationships", []))

    print(
        f"[IR][PARSED] actors={len(ir['threat_actors'])}  "
        f"malware={len(ir['malware'])}  "
        f"tools={len(ir['tools'])}  "
        f"infra={len(ir['infrastructure'])}  "
        f"patterns={len(ir['attack_patterns'])}  "
        f"behaviors={len(ir['behaviors'])}  "
        f"relationships={len(ir['relationships'])}"
    )

    return "\n".join(lines)


async def extract_relationships_llm(ir, text):
    prompt = f"""
    Extract CTI relationships ONLY between entities already identified.

    ENTITIES:
    {json.dumps({
        "threat_actors": [x["name"] for x in ir.get("threat_actors",[])],
        "malware": [x["name"] for x in ir.get("malware",[])],
        "tools": [x["name"] for x in ir.get("tools",[])],
        "infrastructure": [x["name"] for x in ir.get("infrastructure",[])],
    }, indent=2)}

    Use canonical verbs:
    uses, deploys, drops, executes, loads, communicates-with,
    associated-with, exfiltrates, encrypts, installs, runs,
    scans, enumerates, injects, moves, harvests.

    Format:
    [
      {"source": "...", "relationship": "...", "target": "..."}
    ]

    CTI TEXT:
    {text}
    """

    response = await ollama_generate_async(prompt)
    try:
        return json.loads(response)
    except:
        return []
