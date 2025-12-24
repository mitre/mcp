import json, re
import httpx

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "gemma3n:latest"


# ============================================================
# Low-level LLM classify call
# ============================================================

async def classify_entity_llm(name: str, category: str):
    """
    Ask the LLM: Is <name> a valid CTI <category>?
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
                json={"model": MODEL, "prompt": prompt, "stream": False}
            )
            response = r.json()
        except Exception as e:
            print(f"[LLM-VALIDATION][ERROR] HTTP failure for '{name}': {e}")
            return "uncertain"

    try:
        parsed = json.loads(response["response"])
        return parsed.get("valid", "uncertain")
    except Exception:
        print(f"[LLM-VALIDATION][WARN] LLM returned non-JSON for '{name}'")
        return "uncertain"


# ============================================================
# High-level correction pass (stdout-only debug)
# ============================================================

async def validate_entities(ir: dict):
    """
    Validate threat_actors, malware, and tools using the LLM.
    Removes false positives.
    Debug output uses ONLY print() so CLI can capture it.
    """

    print("\n[DEBUG][LLM-VALIDATION] Starting entity validation...")

    validate_map = {}
    categories = [
        ("threat_actors", "threat_actor"),
        ("malware",       "malware"),
        ("tools",         "tool"),
    ]

    # ------------------------------------------------------------
    # First pass — call LLM for each unique normalized name
    # ------------------------------------------------------------
    for group_key, category in categories:
        for ent in ir.get(group_key, []):
            name = (ent.get("name") or "").strip()
            if not name:
                continue

            normalized = name.lower()
            key = (category, normalized)

            if key not in validate_map:
                print(f"[DEBUG][LLM-VALIDATION] Checking {category}: '{name}'")
                result = await classify_entity_llm(name, category)
                validate_map[key] = result
                print(f"[DEBUG][LLM-VALIDATION] {category} '{name}' → {result}")

    # ------------------------------------------------------------
    # Second pass — remove invalid entries
    # ------------------------------------------------------------
    for group_key, category in categories:
        original = ir.get(group_key, [])
        kept, removed = [], []

        for ent in original:
            name = (ent.get("name") or "").strip()
            normalized = name.lower()
            decision = validate_map.get((category, normalized), "yes")

            if decision == "yes":
                kept.append(ent)
            else:
                removed.append((name, decision))

        ir[group_key] = kept

        for name, decision in removed:
            print(f"[DEBUG][LLM-VALIDATION] REMOVED {category}: '{name}' ({decision})")

    print("[DEBUG][LLM-VALIDATION] Entity validation complete.\n")
    return ir

def repair_entities(ir):
    def clean_name(raw):
        name = raw.strip()
        name = name.split(",")[0]           # remove lists
        name = re.sub(r"[^A-Za-z0-9 _-]", "", name)
        words = name.split()
        if len(words) > 4:                  # sentence → reject
            return None
        return name

    fixed = {}
    for group in ("threat_actors", "malware", "tools", "infrastructure"):
        cleaned = []
        for ent in ir.get(group, []):
            n = ent.get("name", "")
            cn = clean_name(n)
            if cn:
                ent["name"] = cn
                cleaned.append(ent)
        fixed[group] = cleaned

    ir.update(fixed)
    return ir
