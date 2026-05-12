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
from collections import defaultdict
from plugins.mcp.app.utilities.llm_client import llm_generate
from functools import lru_cache
from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy


# ============================================================
# LOW-LEVEL LLM CLASSIFICATION
# ============================================================
@lru_cache(maxsize=1)
def _mitre_name_sets():
    tax = load_mitre_taxonomy()
    groups = {o.get("name","").strip().lower() for o in tax.get("groups", {}).values()}
    malware = {o.get("name","").strip().lower() for o in tax.get("malware", {}).values()}
    tools = {o.get("name","").strip().lower() for o in tax.get("tools", {}).values()}
    return groups, malware, tools
async def classify_entity_llm(name: str, category: str) -> str:
    """
    Ask the LLM whether <name> is a valid CTI entity.
    Returns: "yes" | "no" | "uncertain"
    """

    # -----------------------------
    # Deterministic fast-path (MITRE)
    # -----------------------------
    n = (name or "").strip().lower()
    groups, malware, tools = _mitre_name_sets()

    if category == "threat_actor" and n in groups:
        return "yes"
    if category == "malware" and n in malware:
        return "yes"
    if category == "tool" and n in tools:
        return "yes"

    # -----------------------------
    # LLM validation via central client
    # -----------------------------
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

    raw = await llm_generate(prompt, profile="cti")
    if not raw:
        print(f"[ENT][LLM][WARN] empty response for '{name}'")
        return "uncertain"

    try:
        parsed = json.loads(raw)
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
        name = name.split(",")[0]                       # remove lists
        # Preserve '.' (filename extensions like ADRecon.ps1, mstsc.exe),
        # underscores, hyphens, and spaces. Strip only true punctuation
        # noise (quotes, commas, parens, slashes, etc.). The dot is
        # significant -- stripping it collapses "ADRecon.ps1" to
        # "ADReconps1" which then no longer matches the ATT&CK
        # name_index nor the AE-plan reference, breaking software
        # extraction recall.
        name = re.sub(r"[^A-Za-z0-9 ._-]", "", name)    # strip punctuation
        # Squeeze runs of internal whitespace introduced by stripping.
        name = re.sub(r"\s+", " ", name).strip()
        words = name.split()

        # Analyst rule: reject sentence-like entities
        if len(words) > 4:
            return None

        return name
    ENTITY_GROUPS = ("threat_actors", "malware", "tools", "infrastructure")

    total_before = sum(len(ir.get(g, [])) for g in ENTITY_GROUPS)

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

    total_after = sum(len(ir.get(g, [])) for g in ENTITY_GROUPS)

    print(f"[ENT] repair_before={total_before} repair_after={total_after}")
    return ir
