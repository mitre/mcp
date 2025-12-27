"""
cti_entity_validator.py — Entity Validation & Repair (Stage 1)

Responsibilities:
  • Validate CTI entities (actors, malware, tools) via LLM
  • Apply analyst-style uncertainty handling
  • Prevent silent entity loss
  • Repair malformed or overlong entity names
  • Emit explicit debug output for every decision
"""

import json
import re
import httpx
from collections import defaultdict

# ============================================================
# LLM CONFIGURATION
# ============================================================

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "gemma3n:latest"


# ============================================================
# LOW-LEVEL LLM CLASSIFICATION
# ============================================================

async def classify_entity_llm(name: str, category: str) -> str:
    """
    Ask the LLM whether <name> is a valid CTI entity.

    category ∈ {"threat_actor", "malware", "tool"}
    Returns: "yes" | "no" | "uncertain"
    """

    prompt = f"""
You are validating Cyber Threat Intelligence (CTI) entities.
Respond ONLY in JSON.

Task:
Determine if "{name}" is legitimately a {category.replace("_", " ")}.

Valid return values:
- "yes"
- "no"
- "uncertain"

Respond exactly:
{{"valid": "yes" | "no" | "uncertain"}}
""".strip()

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            r = await client.post(
                OLLAMA_URL,
                json={"model": MODEL, "prompt": prompt, "stream": False},
            )
            response = r.json()
        except Exception as e:
            print(f"[ENT][LLM][ERROR] HTTP failure for '{name}': {e}")
            return "uncertain"

    try:
        parsed = json.loads(response.get("response", ""))
        return parsed.get("valid", "uncertain")
    except Exception:
        print(f"[ENT][LLM][WARN] Non-JSON response for '{name}'")
        return "uncertain"


# ============================================================
# ENTITY VALIDATION PIPELINE
# ============================================================

async def validate_entities(ir: dict, destructive: bool = True) -> dict:
    """
    Validate entities using the LLM.

    Rules:
      • "yes"       → keep
      • "uncertain" → keep, confidence downgraded
      • "no"        → remove ONLY if destructive=True
    """

    print("\n[ENT] Starting entity validation")

    categories = [
        ("threat_actors", "threat_actor"),
        ("malware",       "malware"),
        ("tools",         "tool"),
    ]

    # --------------------------------------------------------
    # Pass 1: collect unique names
    # --------------------------------------------------------
    to_validate = {}
    for group, cat in categories:
        for ent in ir.get(group, []):
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            key = (cat, name.lower())
            if key not in to_validate:
                to_validate[key] = name

    print(f"[ENT] unique_entities={len(to_validate)}")

    # --------------------------------------------------------
    # Pass 2: LLM classification (cached per run)
    # --------------------------------------------------------
    decisions = {}
    for (cat, _), name in to_validate.items():
        print(f"[ENT][LLM] validating {cat}: '{name}'")
        result = await classify_entity_llm(name, cat)
        decisions[(cat, name.lower())] = result
        print(f"[ENT][LLM] {cat} '{name}' → {result}")

    # --------------------------------------------------------
    # Pass 3: apply decisions
    # --------------------------------------------------------
    stats = defaultdict(int)

    for group, cat in categories:
        kept = []
        removed = []

        for ent in ir.get(group, []):
            name = (ent.get("name") or "").strip()
            key = (cat, name.lower())
            decision = decisions.get(key, "yes")

            if decision == "yes":
                kept.append(ent)
                stats["kept"] += 1

            elif decision == "uncertain":
                ent["confidence"] = min(ent.get("confidence", 1.0), 0.6)
                kept.append(ent)
                stats["uncertain"] += 1

            else:  # "no"
                stats["rejected"] += 1
                if destructive:
                    removed.append(name)
                else:
                    kept.append(ent)

        ir[group] = kept

        for name in removed:
            print(f"[ENT][DROP] {cat}: '{name}'")

    print(
        f"[ENT] kept={stats['kept']} "
        f"uncertain={stats['uncertain']} "
        f"rejected={stats['rejected']}\n"
    )

    return ir


# ============================================================
# ENTITY NAME REPAIR (NON-DESTRUCTIVE)
# ============================================================

def repair_entities(ir: dict) -> dict:
    """
    Clean malformed entity names without inventing or reclassifying.
    """

    def clean_name(raw: str) -> str | None:
        if not raw:
            return None

        name = raw.strip()
        name = name.split(",")[0]                    # remove lists
        name = re.sub(r"[^A-Za-z0-9 _-]", "", name)  # strip punctuation
        words = name.split()

        # Analyst rule: reject sentence-like entities
        if len(words) > 4:
            return None

        return name

    total_before = sum(len(ir.get(g, [])) for g in ir)

    for group in ("threat_actors", "malware", "tools", "infrastructure"):
        cleaned = []
        for ent in ir.get(group, []):
            raw = ent.get("name", "")
            fixed = clean_name(raw)
            if fixed:
                ent["name"] = fixed
                cleaned.append(ent)
            else:
                print(f"[ENT][REPAIR] dropped malformed '{raw}' ({group})")

        ir[group] = cleaned

    total_after = sum(len(ir.get(g, [])) for g in ir)

    print(f"[ENT] repair_before={total_before} repair_after={total_after}")
    return ir
