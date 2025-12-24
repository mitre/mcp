import re
import numpy as np
import spacy
nlp = spacy.load("en_core_web_lg")

# ---------------------------------------------------------
# Extract explicit technique IDs from text
# ---------------------------------------------------------

def extract_ids_from_text(text, lookup):
    """
    Only match FULL technique IDs like T1059, T1059.001 etc.
    Avoid substring false positives (e.g., T10 inside random text).
    """
    text = text.upper()
    found = set()

    matches = re.findall(r"\bT\d{4}(?:\.\d{3})?\b", text)
    for m in matches:
        if m in lookup:
            found.add(m)

    return list(found)

# ---------------------------------------------------------
# Scoring function — core ranking logic
# ---------------------------------------------------------
def technique_score(tech, text_tokens, behavior_tokens):
    """
    Computes a weighted score for mapping behaviors → MITRE techniques.
    Designed for high CTI fidelity and low false positives.
    """
    score = 0.0

    # -----------------------------------------------------
    # 1. Exact token overlap between technique name tokens
    # -----------------------------------------------------
    overlap = tech["tokens"] & text_tokens
    if overlap:
        score += 6.0

    # -----------------------------------------------------
    # 2. Exact overlap with behavior tokens
    # -----------------------------------------------------
    b_overlap = tech["tokens"] & behavior_tokens
    if b_overlap:
        score += 4.0

    # -----------------------------------------------------
    # 3. Fuzzy token match (shared prefixes >4 chars)
    # -----------------------------------------------------
    for t in tech["tokens"]:
        for b in behavior_tokens:
            if len(t) > 4 and len(b) > 4:
                if t[:5] == b[:5]:
                    score += 1.5

    # -----------------------------------------------------
    # 4. Description token overlap
    # -----------------------------------------------------
    if tech["desc_tokens"] & behavior_tokens:
        score += 2.5

    # -----------------------------------------------------
    # 5. Semantic similarity between behavior text and description
    # -----------------------------------------------------
    if behavior_tokens:
        beh_doc = nlp(" ".join(behavior_tokens))
        if hasattr(tech["vector"], "vector"):
            sim = beh_doc.similarity(tech["vector"])
        else:
            # numpy fallback (very rare after update)
            sim = cosine_sim(beh_doc.vector, tech["vector"])
        if sim > 0.55:
            score += sim * 4.0

    return score

def cosine_sim(a, b):
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# ---------------------------------------------------------
# Behavior → technique mapping
# ---------------------------------------------------------

def map_behaviors_to_techniques(behaviors, techniques, text):
    text_tokens = set(text.lower().split())

    behavior_tokens = set()
    for b in behaviors:
        if isinstance(b, dict):
            tokens = re.findall(r"[a-z0-9]+", b.get("description", "").lower())
            behavior_tokens.update(tokens)
        else:
            behavior_tokens.update(str(b).lower().split())
            

    scored = []
    for tech in techniques:
        platforms = tech.get("platforms", [])

        # Platform filter (soft)
        if platforms:
            # soft filter: multiplatform techniques should stay
            hit = any(p.lower() in text.lower() for p in platforms)
            if not hit and len(platforms) == 1:
                continue

        s = technique_score(tech, text_tokens, behavior_tokens)
        if s > 1.0:
            tech = dict(tech)
            tech["confidence"] = s
            print(f"[MITRE-SCORE] {tech['id']} {tech['name']} → {s:.2f}")
            scored.append((s, tech))

    # sort by score
    scored.sort(reverse=True, key=lambda x: x[0])

    # keep top N scored techniques (N=25)
    return [t for s, t in scored[:25]]


# ---------------------------------------------------------
# Main MITRE extractor — Stage-1 entrypoint
# ---------------------------------------------------------

def extract_mitre_techniques(text, behaviors, techniques, lookup):
    explicit = extract_ids_from_text(text, lookup)
    explicit = [lookup[e] for e in explicit if e in lookup]

    inferred = map_behaviors_to_techniques(behaviors, techniques, text)

    combined = []
    seen = set()

    for t in explicit + inferred:
        tid = t["id"]
        if tid not in seen:
            seen.add(tid)
            combined.append(t)
    print(f"[MITRE] explicit={len(explicit)} inferred={len(inferred)} final={len(combined)}")

    return combined

def convert_sets(obj):
    """Recursively convert Python sets to sorted lists."""
    if isinstance(obj, dict):
        return {k: convert_sets(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets(i) for i in obj]
    elif isinstance(obj, set):
        return sorted(list(obj))
    else:
        return obj
