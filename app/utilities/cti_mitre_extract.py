"""
cti_mitre_extract.py — MITRE ATT&CK Technique Extraction

This module:
    • Extracts explicit ATT&CK technique IDs from CTI text
    • Scores and ranks inferred techniques from behaviors
    • Applies analyst-style selectivity and throttling
    • Produces sparse, explainable MITRE mappings for Stage 1 IR
"""

import re
import numpy as np
import spacy
from functools import lru_cache

# -------------------------------------------------------------------
# NLP model (single global load)
# -------------------------------------------------------------------

nlp = spacy.load("en_core_web_lg")
from spacy.lang.en.stop_words import STOP_WORDS as SPACY_STOP_WORDS


# -------------------------------------------------------------------
# Analyst-style hard limits (explicit, enforced)
# -------------------------------------------------------------------

MAX_TECHNIQUES_PER_BEHAVIOR = 2
MAX_TECHNIQUES_PER_TACTIC = 3
MAX_TOTAL_INFERRED = 15
MITRE_DROPPED = []
# -------------------------------------------------------------------
# Vector caching (BIGGEST performance win)
# -------------------------------------------------------------------

@lru_cache(maxsize=4096)
def vectorize(text: str):
    return nlp(text).vector

# -------------------------------------------------------------------
# Extract explicit technique IDs from text
# -------------------------------------------------------------------

def extract_ids_from_text(text: str, lookup: dict) -> list[str]:
    """
    Match ONLY full ATT&CK technique IDs (e.g., T1059, T1059.001).
    Prevents substring false positives.
    """
    if not text:
        return []

    text = text.upper()
    matches = re.findall(r"\bT\d{4}(?:\.\d{3})?\b", text)
    return [m for m in matches if m in lookup]

# -------------------------------------------------------------------
# Cosine similarity (safe)
# -------------------------------------------------------------------

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# -------------------------------------------------------------------
# Scoring function — analyst-centric
# -------------------------------------------------------------------

def technique_score(tech: dict, text_tokens: set, behavior_tokens: set) -> float:
    """
    Compute confidence score for mapping behavior → MITRE technique.
    Analyst realism: behavior anchoring dominates.
    """
    score = 0.0

    tech_tokens = tech.get("tokens", set()) or set()

    # 1) Behavior overlap is the primary signal
    if tech_tokens & behavior_tokens:
        score += 6.0

    # 2) Document overlap is a secondary/tie-break signal
    if tech_tokens & text_tokens:
        score += 2.0

    # 3) Prefix overlap (soft signal)
    for tok in tech_tokens:
        if any(t.startswith(tok[:4]) for t in behavior_tokens):
            score += 0.5
            break

    # 4) Semantic similarity (cached vectors)
    if behavior_tokens and "vector" in tech:
        beh_vec = vectorize(" ".join(sorted(behavior_tokens)))
        sim = cosine_sim(beh_vec, tech["vector"])
        if sim > 0.55:
            score += sim * 3.0

    return score


# -------------------------------------------------------------------
# Behavior → technique inference (analyst-fixed)
# -------------------------------------------------------------------

def map_behaviors_to_techniques(
        behaviors: list,
        techniques: list,
        text: str
    ) -> list[dict]:
    """
    Infer MITRE techniques from behaviors using analyst-style constraints.

    Guarantees:
      • Evidence required
      • Rank first, then select
      • Hard caps per behavior and globally
    """
    if not behaviors or not techniques:
        return []

    text_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    all_scored = []

    # Stop-word set like "a", "the", "and"
    _SW = SPACY_STOP_WORDS

    for b in behaviors:
        if not isinstance(b, dict):
            continue

        evidence = b.get("text") or b.get("description")
        if not evidence:
            MITRE_DROPPED.append({"reason": "missing_evidence", "behavior": str(b)[:200]})
            continue

        # Evidence-quality gate (hard requirement)
        ev_tokens = re.findall(r"[a-z0-9]+", evidence.lower())
        if len(ev_tokens) < 6:
            MITRE_DROPPED.append({"reason": "evidence_too_short", "behavior": evidence[:200]})
            continue

        stop_ratio = sum(1 for t in ev_tokens if t in _SW) / max(len(ev_tokens), 1)
        if stop_ratio >= 0.75:
            MITRE_DROPPED.append({"reason": "evidence_stopword_heavy", "behavior": evidence[:200]})
            continue

        behavior_tokens = set(ev_tokens)
        scored = []

        for tech in techniques:
            # Soft platform gate (analyst realism)
            platforms = tech.get("platforms", [])
            if platforms:
                if not any(p.lower() in text.lower() for p in platforms):
                    if len(platforms) == 1:
                        continue

            s = technique_score(tech, text_tokens, behavior_tokens)

            # HARD behavior anchor: require at least one exact behavior-token overlap
            tech_tokens = tech.get("tokens", set()) or set()
            if not (tech_tokens & behavior_tokens):
                continue

            # Threshold: keep only meaningful matches
            if s >= 3.0:
                tcopy = {"id": tech.get("id"), "name": tech.get("name")}
                # Normalize to [0,1] (with current scoring, ~10 is "very strong")
                tcopy["confidence"] = round(min(s / 10.0, 1.0), 2)
                tcopy["evidence"] = evidence
                scored.append((s, tcopy))

        # Rank and cap PER BEHAVIOR
        scored.sort(key=lambda x: x[0], reverse=True)
        for s, t in scored[:MAX_TECHNIQUES_PER_BEHAVIOR]:
            all_scored.append((s, t))

    # Global ranking and cap
    all_scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in all_scored[:MAX_TOTAL_INFERRED]]
# -------------------------------------------------------------------
# Stage-1 MITRE extractor (entrypoint)
# -------------------------------------------------------------------

def extract_mitre_techniques(
        text: str,
        behaviors: list,
        techniques: list,
        lookup: dict
    ) -> list[dict]:
    """
    Stage-1 MITRE extractor.

    Combines:
      • Explicit ATT&CK IDs found in text
      • Analyst-filtered inferred techniques

    Guarantees:
      • Sparse output
      • Deterministic ordering
      • Explainable confidence scores
    """
    if not text:
        return []

    # Explicit IDs are always allowed
    explicit_ids = extract_ids_from_text(text, lookup)
    explicit = [lookup[e] for e in explicit_ids if e in lookup]

    # Inferred techniques (ranked + capped)
    inferred = map_behaviors_to_techniques(behaviors, techniques, text)

    combined, seen = [], set()
    for t in explicit + inferred:
        tid = t.get("id")
        if tid and tid not in seen:
            seen.add(tid)
            combined.append(t)

    print(
        f"[MITRE] explicit={len(explicit)} "
        f"inferred={len(inferred)} "
        f"final={len(combined)}"
    )

    return combined

# -------------------------------------------------------------------
# Utility: JSON-safe conversion
# -------------------------------------------------------------------

def convert_sets(obj):
    """Recursively convert Python sets to sorted lists."""
    if isinstance(obj, dict):
        return {k: convert_sets(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_sets(i) for i in obj]
    if isinstance(obj, set):
        return sorted(obj)
    return obj
