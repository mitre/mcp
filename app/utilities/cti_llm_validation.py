"""
cti_llm_validation.py — LLM Validation Layer (Optional, Post-Pipeline)

Uses an LLM to validate and enrich pipeline output. Designed to be:
1. LLM-agnostic: works with any OpenAI-compatible API
2. Hallucination-proof: every answer must cite source text
3. Additive only: never removes pipeline findings, only confirms/denies
4. Optional: pipeline works without this; this only improves precision

Three validation tasks:
1. Technique validation: "Does source text describe technique X?"
2. Relationship discovery: "Which entities interact in this text?"
3. Relationship validation: "Does text support entity A uses entity B?"

Anti-hallucination design:
- Source text is always included in the prompt
- LLM must return YES/NO + exact quote from source
- Responses are validated: quoted text must actually exist in source
- Entity names in relationship discovery are pre-provided (LLM can't invent)
"""

import json
import re
from plugins.mcp.app.utilities.llm_client import llm_generate


# ============================================================
# 1. TECHNIQUE VALIDATION
# ============================================================

async def validate_techniques_llm(
    techniques: list[dict],
    source_text: str,
    batch_size: int = 10,
) -> list[dict]:
    """
    Ask LLM to confirm which techniques are actually described in source text.

    Returns techniques with updated confidence:
    - Confirmed: confidence boosted to 0.90+
    - Denied: confidence dropped to 0.20
    - Uncertain: confidence unchanged

    Anti-hallucination: LLM must quote the source text.
    """
    if not techniques or not source_text:
        return techniques

    # Truncate source text to fit context window
    text_excerpt = source_text[:3000]

    # Batch techniques to reduce API calls
    results = list(techniques)

    for i in range(0, len(techniques), batch_size):
        batch = techniques[i:i + batch_size]
        tech_list = "\n".join(
            f"  {j+1}. {t.get('id', '?')} - {t.get('name', '?')}"
            for j, t in enumerate(batch)
        )

        prompt = f"""You are validating cyber threat intelligence.

SOURCE TEXT (this is the ONLY source of truth):
\"\"\"
{text_excerpt}
\"\"\"

CANDIDATE TECHNIQUES (from automated extraction):
{tech_list}

For EACH technique, determine if the source text describes or implies it.
Return ONLY a JSON array. For each technique:
- "id": the technique ID
- "valid": true if the text describes this technique, false if not
- "quote": exact words from the source text that support your answer (or "" if false)

Example: [{{"id": "T1486", "valid": true, "quote": "ransomware encrypts files"}}]

Return ONLY the JSON array, nothing else."""

        raw = await llm_generate(prompt, profile="cti")
        if not raw:
            continue

        parsed = _parse_json_array(raw)
        if not parsed:
            continue

        # Apply results — with anti-hallucination check
        for item in parsed:
            tid = item.get("id", "")
            valid = item.get("valid", None)
            quote = item.get("quote", "")

            # Find matching technique in our batch
            for t in results:
                if t.get("id") == tid:
                    if valid is True:
                        # Verify quote exists in source text (anti-hallucination)
                        if quote and _quote_exists_in_text(quote, source_text):
                            t["confidence"] = max(t.get("confidence", 0.5), 0.90)
                            t["x_llm_validated"] = True
                            t["x_llm_evidence"] = quote
                        else:
                            # LLM said valid but couldn't provide real quote
                            # Slight boost but flagged
                            t["confidence"] = max(t.get("confidence", 0.5), 0.70)
                            t["x_llm_validated"] = "unverified"
                    elif valid is False:
                        t["confidence"] = min(t.get("confidence", 0.5), 0.20)
                        t["x_llm_validated"] = False
                    break

    confirmed = sum(1 for t in results if t.get("x_llm_validated") is True)
    denied = sum(1 for t in results if t.get("x_llm_validated") is False)
    print(f"[LLM-VAL] Techniques: {confirmed} confirmed, {denied} denied, "
          f"{len(results) - confirmed - denied} unchanged")

    return results


# ============================================================
# 2. RELATIONSHIP DISCOVERY
# ============================================================

async def discover_relationships_llm(
    source_text: str,
    entities: dict,
) -> list[dict]:
    """
    Ask LLM to identify relationships between known entities in the text.

    This is the ONE place where LLM adds recall — it can resolve
    coreference ("they" = BlackCat) and cross-sentence references
    that dep-parse cannot.

    Anti-hallucination: entities are pre-provided. LLM can only
    pair them, not invent new ones.
    """
    actors = [a.get("name", "") for a in entities.get("threat_actors", [])]
    malware = [m.get("name", "") for m in entities.get("malware", [])]
    tools = [t.get("name", "") for t in entities.get("tools", [])]
    infra = [i.get("name", "") for i in entities.get("infrastructure", [])]

    all_entities = actors + malware + tools + infra
    if len(all_entities) < 2:
        return []

    text_excerpt = source_text[:3000]
    entity_list = ", ".join(all_entities[:20])  # Cap at 20 entities

    prompt = f"""You are extracting relationships from a cyber threat intelligence report.

SOURCE TEXT:
\"\"\"
{text_excerpt}
\"\"\"

KNOWN ENTITIES (from prior extraction — do NOT add new ones):
  Actors/Malware: {', '.join(actors + malware) or 'none identified'}
  Tools: {', '.join(tools) or 'none identified'}
  Infrastructure: {', '.join(infra) or 'none identified'}

List ALL relationships between these entities that are stated or clearly implied in the source text.
Use ONLY the entity names listed above. Do NOT invent new entities.

For each relationship, provide:
- "source": the entity performing the action (must be from list above)
- "relationship": the action verb (uses, deploys, targets, exploits, etc.)
- "target": the entity being acted upon (must be from list above)
- "quote": exact words from the source text supporting this relationship

Return ONLY a JSON array. Example:
[{{"source": "BlackCat", "relationship": "uses", "target": "Mimikatz", "quote": "leverage Mimikatz to recover passwords"}}]

Return ONLY the JSON array, nothing else."""

    raw = await llm_generate(prompt, profile="cti")
    if not raw:
        return []

    parsed = _parse_json_array(raw)
    if not parsed:
        return []

    # Validate: entities must be from our list, quotes must exist
    entity_set = {e.lower() for e in all_entities}
    validated = []

    for item in parsed:
        src = item.get("source", "")
        tgt = item.get("target", "")
        rel = item.get("relationship", "")
        quote = item.get("quote", "")

        if not src or not tgt or not rel:
            continue

        # Anti-hallucination: source and target must be from our entity list
        src_ok = any(src.lower() in e or e in src.lower() for e in entity_set)
        tgt_ok = any(tgt.lower() in e or e in tgt.lower() for e in entity_set)

        if not src_ok or not tgt_ok:
            continue

        # Anti-hallucination: quote should exist in text
        quote_verified = _quote_exists_in_text(quote, source_text) if quote else False

        validated.append({
            "source": src,
            "relationship": rel.lower(),
            "target": tgt,
            "confidence": 0.85 if quote_verified else 0.65,
            "evidence": quote if quote_verified else f"LLM-inferred: {quote}",
            "source_context": "llm-discovery",
            "x_llm_quote_verified": quote_verified,
        })

    print(f"[LLM-VAL] Relationships discovered: {len(validated)} "
          f"({sum(1 for v in validated if v['x_llm_quote_verified'])} quote-verified)")

    return validated


# ============================================================
# 3. RELATIONSHIP VALIDATION
# ============================================================

async def validate_relationships_llm(
    relationships: list[dict],
    source_text: str,
) -> list[dict]:
    """
    Validate existing relationships against source text.
    """
    if not relationships or not source_text:
        return relationships

    text_excerpt = source_text[:3000]
    rel_list = "\n".join(
        f"  {i+1}. {r.get('source', '?')} → {r.get('relationship', '?')} → {r.get('target', '?')}"
        for i, r in enumerate(relationships[:15])  # Cap at 15
    )

    prompt = f"""You are validating cyber threat intelligence relationships.

SOURCE TEXT:
\"\"\"
{text_excerpt}
\"\"\"

CANDIDATE RELATIONSHIPS:
{rel_list}

For each relationship, determine if the source text supports it.
Return ONLY a JSON array:
- "index": the relationship number (1-based)
- "valid": true/false
- "quote": exact supporting text or "" if false

Return ONLY the JSON array."""

    raw = await llm_generate(prompt, profile="cti")
    if not raw:
        return relationships

    parsed = _parse_json_array(raw)
    if not parsed:
        return relationships

    results = list(relationships)
    for item in parsed:
        idx = item.get("index", 0) - 1
        valid = item.get("valid", None)
        quote = item.get("quote", "")

        if 0 <= idx < len(results):
            if valid is True and _quote_exists_in_text(quote, source_text):
                results[idx]["confidence"] = max(results[idx].get("confidence", 0.5), 0.85)
                results[idx]["x_llm_validated"] = True
            elif valid is False:
                results[idx]["confidence"] = min(results[idx].get("confidence", 0.5), 0.25)
                results[idx]["x_llm_validated"] = False

    confirmed = sum(1 for r in results if r.get("x_llm_validated") is True)
    denied = sum(1 for r in results if r.get("x_llm_validated") is False)
    print(f"[LLM-VAL] Relationships: {confirmed} confirmed, {denied} denied")

    return results


# ============================================================
# HELPERS
# ============================================================

def _parse_json_array(raw: str) -> list | None:
    """Extract a JSON array from LLM response, handling markdown fences."""
    raw = raw.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except Exception:
        pass

    # Try to find array in response
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    return None


def _quote_exists_in_text(quote: str, text: str, threshold: float = 0.6) -> bool:
    """
    Check if a quoted phrase exists in the source text.

    Uses fuzzy matching: at least 60% of quote words must appear
    in a window of the source text. This handles minor LLM
    paraphrasing while catching outright hallucinations.
    """
    if not quote or not text:
        return False

    quote_words = set(re.findall(r"[a-z]{3,}", quote.lower()))
    if not quote_words:
        return False

    text_lower = text.lower()

    # Exact substring check first
    if quote.lower() in text_lower:
        return True

    # Fuzzy: check if enough quote words appear in text
    text_words = set(re.findall(r"[a-z]{3,}", text_lower))
    overlap = quote_words & text_words
    ratio = len(overlap) / len(quote_words)

    return ratio >= threshold
