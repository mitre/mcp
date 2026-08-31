"""
cti_mitre_extract.py — MITRE ATT&CK Technique Extraction

Stage-1 MITRE extraction with analyst-style selectivity.

Responsibilities:
  • Extract explicit ATT&CK IDs from text
  • Infer techniques from QUALIFIED behaviors only
  • Enforce sparsity, plausibility, and evidence quality
  • Provide explainable confidence + rejection logging

This module performs NO orchestration.
"""

import re
import numpy as np

from plugins.mcp.app.utilities.nlp_model import get_nlp
from datetime import datetime, timezone
import uuid
from functools import lru_cache
from spacy.lang.en.stop_words import STOP_WORDS as SPACY_STOP_WORDS


# ============================================================
# NLP MODEL (GLOBAL SINGLE LOAD)
# ============================================================



# ============================================================
# ANALYST LIMITS (EXPLICIT + ENFORCED)
# ============================================================

MAX_TECHNIQUES_PER_BEHAVIOR = 2
MAX_TOTAL_INFERRED = 15



# ============================================================
# VECTOR CACHE (PERFORMANCE CRITICAL)
# ============================================================

@lru_cache(maxsize=4096)
def vectorize(text: str):
    return get_nlp()(text).vector


# ============================================================
# NUMERIC SAFETY
# ============================================================

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ============================================================
# EXPLICIT ATT&CK ID EXTRACTION (STRICT)
# ============================================================

def extract_ids_from_text(text: str, lookup: dict) -> list[str]:
    """
    Match ONLY full ATT&CK IDs (T1059, T1059.001).
    No substrings, no inference.
    """
    if not text:
        return []

    matches = re.findall(r"\bT\d{4}(?:\.\d{3})?\b", text.upper())
    valid = [m for m in matches if m in lookup]

    if valid:
        print(f"[MITRE] explicit_ids={len(valid)}")

    return valid


# ============================================================
# TECHNIQUE SCORING (ANALYST-CENTRIC)
# ============================================================

def technique_score(
    tech: dict,
    behavior_tokens: set,
    document_tokens: set
) -> float:
    """
    Score behavior → technique alignment.

    Analyst priority:
      1. Direct behavior token overlap
      2. Secondary document anchoring
      3. Semantic similarity (soft bounded)
    """
    score = 0.0
    tech_tokens = tech.get("tokens", set()) or set()

    # --- 1) HARD behavior anchoring ---
    if tech_tokens & behavior_tokens:
        score += 6.0

    # --- 2) Secondary document overlap ---
    if tech_tokens & document_tokens:
        score += 2.0

    # --- 3) Prefix soft match ---
    for tok in tech_tokens:
        if any(b.startswith(tok[:4]) for b in behavior_tokens):
            score += 0.5
            break

    # --- 4) Semantic similarity (soft bounded) ---
    if "vector" in tech and behavior_tokens:
        beh_vec = vectorize(" ".join(sorted(behavior_tokens)))
        sim = cosine_sim(beh_vec, tech["vector"])

        if sim >= 0.65:
            weight = 1.0
        elif sim >= 0.45:
            weight = 0.7
        elif sim >= 0.30:
            weight = 0.4
        else:
            weight = 0.1

        score += sim * 3.0 * weight

    return score


# ============================================================
# BEHAVIOR → TECHNIQUE INFERENCE (QUALIFIED ONLY)
# ============================================================

def map_behaviors_to_techniques(
    behaviors: list[dict],
    techniques: list[dict],
    text: str
) -> list[dict]:
    """
    Infer MITRE techniques from QUALIFIED behaviors.

    Guarantees:
      • Evidence required
      • Ranked before selection
      • Hard global + per-behavior caps
    """
    dropped_here: list[dict] = []
    if not behaviors or not techniques:
        return []

    doc_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    all_scored: list[tuple[float, dict]] = []

    for b in behaviors:
        evidence = b.get("text") or b.get("description")
        if not evidence:
            dropped_here.append({"reason": "missing_evidence"})
            continue

        ev_tokens = re.findall(r"[a-z0-9]+", evidence.lower())
        d = get_nlp()(evidence)
        has_vo = False
        for tok in d:
            if tok.pos_ == "VERB" and any(c.dep_ in ("dobj", "pobj", "attr") for c in tok.children):
                has_vo = True
                break
        if not has_vo:
            dropped_here.append({
                "reason": "missing_verb_object_anchor",
                "behavior": evidence[:160],
            })
            continue
        if len(ev_tokens) < 4:
            dropped_here.append({
                "reason": "evidence_too_short_for_mitre",
                "behavior": evidence
            })
            continue

        short_evidence = len(ev_tokens) < 6
        if short_evidence:
            dropped_here.append({
                "reason": "evidence_short_downweighted",
                "behavior": evidence[:160]
            })

        stop_ratio = sum(1 for t in ev_tokens if t in SPACY_STOP_WORDS) / len(ev_tokens)
        if stop_ratio >= 0.75:
            dropped_here.append({
                "reason": "stopword_heavy",
                "behavior": evidence[:160]
            })
            continue

        behavior_tokens = {
            t for t in ev_tokens
            if t not in {"analyze", "observe", "identify", "report", "highlight", "find"}
        }

        scored: list[tuple[float, dict]] = []

        for tech in techniques:
            platforms = tech.get("platforms", [])
            if platforms:
                if not any(p.lower() in text.lower() for p in platforms):
                    if len(platforms) == 1:
                        continue

            s = technique_score(tech, behavior_tokens, doc_tokens)

            # HARD operational anchor
            if not (tech.get("tokens", set()) & behavior_tokens):
                continue

            # Soft kill-chain plausibility
            b_phases = {b.get("kill_chain_phase") for b in behaviors if b.get("kill_chain_phase")}
            tactics = set(tech.get("tactics", []))
            if b_phases and tactics:
                if not any(p in t.lower() for p in b_phases for t in tactics):
                    s *= 0.5

            spec_penalty = evidence_specificity_score(evidence)
            s *= spec_penalty

            if s >= 3.0:
                scored.append((s, tech))

        scored.sort(key=lambda x: x[0], reverse=True)
        all_scored.extend(scored[:MAX_TECHNIQUES_PER_BEHAVIOR])

    all_scored.sort(key=lambda x: x[0], reverse=True)
    final = [t for _, t in all_scored[:MAX_TOTAL_INFERRED]]

    # This counter used to be module state, and Stage 1 runs files on a thread
    # pool, so it reported every drop since process start rather than this
    # file's. Nothing outside this module ever read it.
    print(f"[MITRE] inferred={len(final)} dropped={len(dropped_here)}")
    return final


# ============================================================
# STAGE-1 ENTRYPOINT
# ============================================================

def extract_mitre_techniques(
    text: str,
    behaviors: list[dict],
    techniques: list[dict],
    lookup: dict
) -> list[dict]:
    """
    Stage-1 MITRE extractor.

    Combines:
      • Explicit ATT&CK IDs (always accepted)
      • Inferred techniques from QUALIFIED behaviors

    Output is sparse, ranked, explainable.
    """
    if not text:
        return []

    explicit_ids = extract_ids_from_text(text, lookup)
    explicit = [lookup[i] for i in explicit_ids if i in lookup]

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


# ============================================================
# JSON-SAFE CONVERSION
# ============================================================

def convert_sets(obj):
    if isinstance(obj, dict):
        return {k: convert_sets(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_sets(i) for i in obj]
    if isinstance(obj, set):
        return sorted(obj)
    return obj

def hashes_to_stix_observed_data(hashes, source_name="cti-report"):
    objects = []

    for h in hashes:
        file_id = f"file--{uuid.uuid4()}"
        obs_id = f"observed-data--{uuid.uuid4()}"

        file_obj = {
            "type": "file",
            "id": file_id,
            "hashes": {
                h["hash_type"]: h["hash"]
            }
        }

        stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        observed = {
            "type": "observed-data",
            "spec_version": "2.1",
            "id": obs_id,
            "created": stamp,
            "modified": stamp,
            # Required by the 2.1 spec. Without them stix2.parse raises
            # MissingPropertiesError, so any bundle carrying a file hash could
            # not be loaded by the reference parser at all.
            "first_observed": stamp,
            "last_observed": stamp,
            "number_observed": 1,
            "objects": {
                "0": file_obj
            },
            "x_cti_evidence": h["evidence"],
            "labels": ["malicious-activity"]
        }

        objects.append(observed)

    return objects

def evidence_specificity_score(text: str) -> float:
    """
    Returns a multiplier in [0.6, 1.0]
    Penalizes abstract / generic evidence structurally, not lexically.
    """
    doc = get_nlp()(text)

    verbs = [t for t in doc if t.pos_ == "VERB"]
    nouns = [t for t in doc if t.pos_ in ("NOUN", "PROPN")]
    concrete_objs = [
        c for v in verbs
        for c in v.children
        if c.dep_ in ("dobj", "pobj", "attr")
    ]

    score = 1.0

    # No verb-object relation → very generic
    if not concrete_objs:
        score -= 0.25

    # Too many abstract nouns vs concrete ones
    abstract_nouns = [
        n for n in nouns
        if n.lemma_.endswith(("ity", "ness", "tion", "ment"))
    ]

    if abstract_nouns and len(abstract_nouns) >= len(nouns) / 2:
        score -= 0.15

    # Single vague verb (e.g., "weaken", "affect", "impact") with no modifiers
    if len(verbs) == 1:
        v = verbs[0]
        if not any(c.dep_ in ("dobj", "pobj") for c in v.children):
            score -= 0.15

    return max(0.6, score)
