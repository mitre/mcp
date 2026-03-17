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
    # Also collect aliases for fuzzy matching
    all_aliases = set()
    for collection in (tax.get("groups", {}), tax.get("malware", {}), tax.get("tools", {})):
        for obj in collection.values():
            for alias in obj.get("x_mitre_aliases", []):
                all_aliases.add(alias.strip().lower())
            name = obj.get("name", "").strip().lower()
            if name:
                all_aliases.add(name)
    return groups, malware, tools, all_aliases


def _known_cti_entity(name: str) -> bool:
    """Check if a name is a known CTI entity (tool, malware, or group) by any name/alias."""
    n = (name or "").strip().lower()
    if not n or len(n) < 2:
        return False
    _, _, _, all_aliases = _mitre_name_sets()
    # Exact match
    if n in all_aliases:
        return True
    # Common misspellings: try without double letters
    norm = re.sub(r"(.)\1+", r"\1", n)
    if norm in all_aliases:
        return True
    # Try without trailing version/suffix
    base = re.sub(r"[.\-_]\w+$", "", n)
    if base in all_aliases:
        return True
    return False


async def classify_entity_llm(name: str, category: str) -> str:
    """
    Ask the LLM whether <name> is a valid CTI entity.
    Returns: "yes" | "no" | "uncertain"
    """

    # -----------------------------
    # Deterministic fast-path (MITRE)
    # -----------------------------
    n = (name or "").strip().lower()
    groups, malware, tools, all_aliases = _mitre_name_sets()

    # Exact match in correct category
    if category == "threat_actor" and n in groups:
        return "yes"
    if category == "malware" and n in malware:
        return "yes"
    if category == "tool" and n in tools:
        return "yes"

    # Cross-category: known entity, just miscategorized → still valid
    if n in all_aliases:
        return "yes"

    # Fuzzy: handle misspellings (e.g., "Mimiikatz" → "mimikatz")
    norm = re.sub(r"(.)\1+", r"\1", n)
    if norm in all_aliases:
        return "yes"

    # Common tool names that aren't in MITRE but are widely known
    WELL_KNOWN = {
        "anydesk", "teamviewer", "rsync", "wmic", "fsutil", "vim-cmd",
        "wevtutil", "veeam", "megasync", "rclone", "gmer", "keepass",
        "winrar", "7zip", "nmap", "netcat", "wget", "curl", "ssh",
        "scp", "powershell", "cmd.exe", "bitsadmin", "certutil",
        "vssadmin", "bcdedit", "reg.exe", "sc.exe", "net.exe",
        "wscript", "cscript", "mshta", "rundll32", "regsvr32",
        "brute ratel", "sliver", "metasploit", "empire",
    }
    if n in WELL_KNOWN or n.rstrip(".exe") in WELL_KNOWN:
        return "yes"

    # Skip LLM for names that look like file paths or system utilities
    if re.match(r"^[a-z][a-z0-9._-]{1,20}(\.exe|\.dll|\.ps1|\.vbs|\.bat)?$", n):
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
# ENTITY RECLASSIFICATION (DETERMINISTIC, PRE-LLM)
# ============================================================

def reclassify_entities(ir: dict) -> dict:
    """
    Move misclassified entities between IR categories using MITRE taxonomy.
    Runs BEFORE LLM validation to reduce LLM calls and fix type errors.
    """
    groups, malware_names, tool_names, _ = _mitre_name_sets()

    new_malware = []
    for m in ir.get("malware", []):
        name = (m.get("name") or "").strip()
        name_lower = name.lower()

        # Known MITRE tool misclassified as malware → move to tools
        if name_lower in tool_names:
            ir.setdefault("tools", []).append(m)
            print(f"[RECLASS] malware→tool: '{name}' (MITRE taxonomy match)")
            continue

        # Technique descriptions misclassified as malware → drop from entities
        technique_indicators = ["deletion", "disabling", "recovery", "clearing",
                                "modification", "enumeration", "escalation"]
        if any(ind in name_lower for ind in technique_indicators):
            print(f"[RECLASS] malware→dropped: '{name}' (technique description)")
            continue

        # Slash-separated compound names → split
        if "/" in name and len(name) < 50:
            parts = [p.strip() for p in name.split("/") if p.strip()]
            for part in parts:
                part_lower = part.lower()
                if part_lower in tool_names:
                    ir.setdefault("tools", []).append(
                        {"name": part, "description": m.get("description", "")})
                    print(f"[RECLASS] split→tool: '{part}'")
                elif part_lower in malware_names:
                    new_malware.append(
                        {"name": part, "description": m.get("description", "")})
                else:
                    ir.setdefault("tools", []).append(
                        {"name": part, "description": m.get("description", "")})
                    print(f"[RECLASS] split→tool (default): '{part}'")
            continue

        # Script/executable files → tools
        if re.search(r'\.(exe|ps1|vbs|dll|bat|cmd)$', name_lower):
            ir.setdefault("tools", []).append(m)
            print(f"[RECLASS] malware→tool: '{name}' (script/executable)")
            continue

        new_malware.append(m)

    ir["malware"] = new_malware
    return ir


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
        name = re.sub(r"[^A-Za-z0-9. _-]", "", name)  # strip punctuation, keep dots for IPs/domains
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
