"""
cti_linguistics.py — Entity Canonicalization, Behavior Normalization,
and Dynamic Linguistic Technique Extraction.

This module provides:

  • Behavior text normalization
  • Entity canonicalization via fuzzy matching
  • Relationship endpoint normalization
  • Entity-type identification
  • Fully dynamic MITRE technique candidate extraction based solely on:
        - noun chunks
        - verb-object pairs
        - syscall/API keywords
        - natural-language behavior phrases
        - semantic similarity to MITRE ATT&CK technique descriptions

NO static keyword lists, NO brittle mappings.

This is the Stage-1 linguistic technique extractor.
"""

import re
import numpy as np
import spacy
from rapidfuzz import fuzz

nlp = spacy.load("en_core_web_lg")


# ============================================================
# Behavior normalization
# ============================================================

def normalize_behavior_text(text: str) -> str:
    """Normalize LLM-extracted behavior descriptions."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


# ============================================================
# Fuzzy entity resolution
# ============================================================

def fuzzy_resolve(name: str, candidates):
    """RapidFuzz-based fuzzy matching used for canonicalization."""
    if not name:
        return None
    name_l = name.lower()
    best = None
    best_score = 0

    for c in candidates:
        cname = c.get("name", "").lower()
        s = fuzz.partial_ratio(name_l, cname)
        if s > best_score and s >= 80:
            best = c
            best_score = s
    return best


def canonicalize_entity(name: str, ir: dict):
    if not name:
        return name
    pool = (
        ir.get("threat_actors", [])
        + ir.get("malware", [])
        + ir.get("tools", [])
        + ir.get("infrastructure", [])
    )
    hit = fuzzy_resolve(name, pool)
    return hit.get("name") if hit else name


def canonicalize_relationship_endpoints(ir, rels=None):
    if rels is None:
        rels = ir.get("relationships", [])
    for r in rels:
        r["source"] = canonicalize_entity(r.get("source"), ir)
        r["target"] = canonicalize_entity(r.get("target"), ir)
    return rels


# ============================================================
# Entity type identification
# ============================================================

def normalize_entity_type(name: str, ir: dict) -> str:
    if not name:
        return "unknown"
    name_l = name.lower().strip()

    def match(group):
        return any(
            isinstance(e, dict) and e.get("name", "").lower() == name_l
            for e in ir.get(group, [])
        )

    if match("threat_actors"): return "threat_actor"
    if match("malware"):        return "malware"
    if match("tools"):          return "tool"
    if match("infrastructure"): return "infrastructure"
    if match("attack_patterns"):return "attack_pattern"
    return "unknown"


# ============================================================
# Dynamic Linguistic Technique Extraction
# ============================================================

def extract_candidate_phrases(text: str):
    """
    Extract linguistic features from CTI text:
    - noun chunks ("remote command execution")
    - verb → object pairs ("inject process")
    - syscall/API identifiers ("CreateFile", "sys_open", "connect")
    - 2–4 token sliding windows
    """
    doc = nlp(text)
    phrases = set()

    # --- Noun chunks ---
    for ch in doc.noun_chunks:
        t = ch.text.strip().lower()
        if len(t.split()) >= 2:
            phrases.add(t)

    # --- Verb-object pairs ---
    for tok in doc:
        if tok.pos_ != "VERB":
            continue
        obj = None
        for c in tok.children:
            if c.dep_ in ("dobj", "pobj"):
                obj = c.text.lower()
        if obj:
            phrases.add(f"{tok.lemma_.lower()} {obj}")

    # --- Syscall / API tokens ---
    api_hits = re.findall(r"\b[a-zA-Z_][A-Za-z0-9_]{3,}\b", text)
    for a in api_hits:
        phrases.add(a.lower())

    # --- Sliding windows ---
    alpha_tokens = [t.text.lower() for t in doc if t.is_alpha]
    for i in range(len(alpha_tokens) - 3):
        window = " ".join(alpha_tokens[i:i+4])
        phrases.add(window)

    cleaned = []
    for p in phrases:
        if len(p) < 4:
            continue
        if len(p.split()) > 6:
            continue
        if p.isnumeric():
            continue
        cleaned.append(p)

    return cleaned


def phrase_vector(phrase: str):
    """Safe wrapper around spaCy vectors."""
    try:
        return nlp(phrase).vector
    except:
        return np.zeros(300)


def cosine(a, b):
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a)*np.linalg.norm(b)))


def semantic_match_techniques(phrases, techniques, threshold=0.42):
    """
    Performs semantic similarity between linguistic phrases
    and MITRE ATT&CK technique descriptions.
    """
    results = []
    for p in phrases:
        p_vec = phrase_vector(p)
        for tech in techniques:
            t_vec = tech.get("vector", None)
            if t_vec is None:
                continue     # Technique has no embedding → skip
            t_vec = np.asarray(t_vec, dtype=float)
            sim = cosine(p_vec, t_vec)

            if sim >= threshold:
                results.append({
                    "tech": tech,
                    "phrase": p,
                    "score": sim
                })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def extract_dynamic_techniques(text: str, techniques: list, limit=25):
    """
    Full extraction pipeline:
        1. extract_candidate_phrases()
        2. semantic_match_techniques()
        3. return top N unique techniques
    """
    phrases = extract_candidate_phrases(text)
    print(f"[LING] candidate phrases extracted: {len(phrases)}")

    matches = semantic_match_techniques(phrases, techniques)
    print(f"[LING] semantic matches above threshold: {len(matches)}")


    seen = set()
    out = []
    for m in matches:
        tid = m["tech"]["id"]
        if tid not in seen:
            seen.add(tid)
            out.append({
                "id": tid,
                "name": m["tech"]["name"],
                "confidence": round(float(m["score"]), 4),
                "evidence": [m["phrase"]]
            })
        if len(out) >= limit:
            break
    out = [t for t in out if t["confidence"] >= 0.18]

    return out
