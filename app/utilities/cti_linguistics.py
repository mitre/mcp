"""
cti_linguistics.py — Linguistic Signal Extraction for Stage 1

Responsibilities:
  • Behavior text normalization
  • Fuzzy entity canonicalization
  • Relationship endpoint canonicalization
  • Entity-type identification
  • Dynamic linguistic MITRE technique extraction using:
        - noun chunks
        - verb–object pairs
        - structural verbs
        - sliding windows
        - semantic similarity to ATT&CK descriptions

NO static keyword lists.
NO brittle mappings.
"""

import re
import numpy as np
import spacy
import asyncio
from rapidfuzz import fuzz
from functools import lru_cache

# ============================================================
# NLP MODEL (GLOBAL SINGLE LOAD)
# ============================================================

nlp = spacy.load("en_core_web_lg")

# ===========================================================
# Attempt to capture command-line invocations
# ===========================================================
COMMAND_REGEXES = [
    # Windows-style commands
    r"\b(?:cmd\.exe|powershell\.exe|pwsh\.exe|psexec\.exe|wmic|sc\.exe)\b[^\n\r\"']{0,200}",
    # Linux-style commands
    r"\b(?:bash|sh|curl|wget|chmod|chown|systemctl)\b[^\n\r\"']{0,200}",
]
def extract_commands(text: str) -> list[dict]:
    """
    Extract exact command-line invocations from CTI text.

    Returns:
        [
          {
            "command": "...",
            "confidence": 0.9,
            "source": "report-text",
            "evidence": "sentence containing command"
          }
        ]
    """
    commands = []
    if not text:
        return commands

    for regex in COMMAND_REGEXES:
        for m in re.finditer(regex, text, flags=re.IGNORECASE):
            cmd = m.group(0).strip()
            if len(cmd.split()) < 2:
                continue

            # grab surrounding evidence sentence
            start = max(0, m.start() - 120)
            end = min(len(text), m.end() + 120)
            evidence = text[start:end].replace("\n", " ").strip()

            commands.append({
                "command": cmd,
                "confidence": 0.9,
                "source": "report-text",
                "evidence": evidence,
            })

    return commands
# ===========================================================
# Attempt to capture hash-like strings
# ===========================================================
HASH_PATTERNS = {
    "MD5": re.compile(r"\b[a-fA-F0-9]{32}\b"),
    "SHA1": re.compile(r"\b[a-fA-F0-9]{40}\b"),
    "SHA256": re.compile(r"\b[a-fA-F0-9]{64}\b"),
    "SHA512": re.compile(r"\b[a-fA-F0-9]{128}\b"),
}
def extract_hashes(text: str) -> list[dict]:
    """
    Extract cryptographic hashes from CTI text.

    Returns:
        [
            {
                "hash_type": "SHA256",
                "hash": "<value>",
                "evidence": "<sentence>"
            }
        ]
    """
    results = []
    seen = set()

    for line in text.splitlines():
        for htype, pattern in HASH_PATTERNS.items():
            for match in pattern.findall(line):
                key = (htype, match)
                if key in seen:
                    continue
                seen.add(key)

                results.append({
                    "hash_type": htype,
                    "hash": match.lower(),
                    "evidence": line.strip(),
                })

    return results

# ============================================================
# BEHAVIOR NORMALIZATION
# ============================================================

def normalize_behavior_text(text: str) -> str:
    """
    Normalize behavior text without destroying semantics.
    """
    return re.sub(r"\s+", " ", text or "").strip().lower()

# ============================================================
# FUZZY ENTITY RESOLUTION
# ============================================================

def fuzzy_resolve(name: str, candidates: list[dict]) -> dict | None:
    if not name:
        return None

    name_l = name.lower()
    best, best_score = None, 0

    for c in candidates:
        cname = c.get("name", "").lower()
        if not cname:
            continue

        s = fuzz.partial_ratio(name_l, cname)
        if s >= 80 and s > best_score:
            best, best_score = c, s

    return best

def canonicalize_entity(name: str, ir: dict) -> str:
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

def canonicalize_relationship_endpoints(ir: dict, rels: list | None = None) -> list:
    if rels is None:
        rels = ir.get("relationships", [])

    for r in rels:
        r["source"] = canonicalize_entity(r.get("source"), ir)
        r["target"] = canonicalize_entity(r.get("target"), ir)

    return rels

# ============================================================
# ENTITY TYPE IDENTIFICATION
# ============================================================

def normalize_entity_type(name: str, ir: dict) -> str:
    if not name:
        return "unknown"

    n = name.lower().strip()

    def match(group):
        return any(
            isinstance(e, dict) and e.get("name", "").lower() == n
            for e in ir.get(group, [])
        )

    if match("threat_actors"): return "threat_actor"
    if match("malware"):        return "malware"
    if match("tools"):          return "tool"
    if match("infrastructure"): return "infrastructure"
    if match("attack_patterns"):return "attack_pattern"
    return "unknown"

# ============================================================
# SAFE spaCy VECTOR ACCESS
# ============================================================

@lru_cache(maxsize=4096)
def phrase_vector(phrase: str) -> np.ndarray:
    try:
        return nlp(phrase).vector
    except Exception:
        return np.zeros(300)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

# ============================================================
# LINGUISTIC PHRASE EXTRACTION (NON-BRITTLE)
# ============================================================

def extract_candidate_phrases(text: str) -> list[str]:
    """
    Extract structurally admissible linguistic phrases.

    Produces OVER-COMPLETE candidates; pruning happens later.
    """
    if not text:
        return []

    raw_phrases = set()

    MAX_CHARS = int(nlp.max_length * 0.8)
    doc_cache = {}

    for offset in range(0, len(text), MAX_CHARS):
        chunk = text[offset:offset + MAX_CHARS]

        if chunk not in doc_cache:
            doc_cache[chunk] = nlp(chunk)

        doc = doc_cache[chunk]

        # --- noun chunks ---
        for ch in doc.noun_chunks:
            t = ch.text.strip().lower()
            if len(t.split()) >= 2:
                raw_phrases.add(t)

        # --- verb → object ---
        for tok in doc:
            if tok.pos_ != "VERB":
                continue
            for c in tok.children:
                if c.dep_ in ("dobj", "pobj"):
                    raw_phrases.add(f"{tok.lemma_.lower()} {c.text.lower()}")

        # --- structural verbs ---
        for tok in doc:
            if tok.pos_ == "VERB" and tok.is_alpha and not tok.is_stop:
                raw_phrases.add(tok.lemma_.lower())

        # --- sliding windows ---
        alpha = [t for t in doc if t.is_alpha]
        for i in range(len(alpha) - 3):
            window = alpha[i:i + 4]
            if any(t.pos_ == "VERB" for t in window):
                raw_phrases.add(" ".join(t.text.lower() for t in window))

    print(f"[LING] raw_phrases={len(raw_phrases)}")

    # ========================================================
    # STRUCTURAL OPERATIONAL FILTER
    # ========================================================
    cleaned = []

    for p in raw_phrases:
        doc_p = nlp(p)

        if not any(t.pos_ == "VERB" for t in doc_p):
            continue
        if not any(t.dep_ in ("dobj", "pobj") for t in doc_p):
            continue
        if len(p) < 4 or len(p.split()) > 6 or p.isnumeric():
            continue

        cleaned.append(p)

    print(f"[LING] operational_phrases={len(cleaned)}")
    return cleaned

# ============================================================
# SEMANTIC MATCHING AGAINST MITRE
# ============================================================

async def _semantic_match_phrase(
        phrase: str,
        p_vec: np.ndarray,
        techniques: list[dict],
        threshold: float
    ) -> list[dict]:

    matches = []
    for tech in techniques:
        t_vec = tech.get("vector")
        if t_vec is None:
            continue

        sim = cosine(p_vec, np.asarray(t_vec, dtype=float))
        dyn_thresh = threshold + 0.15 if len(phrase.split()) <= 2 else threshold

        if sim >= dyn_thresh:
            matches.append({
                "tech": tech,
                "phrase": phrase,
                "score": sim,
            })

    return matches

async def semantic_match_techniques(
        phrases: list[str],
        techniques: list[dict],
        threshold: float = 0.42
    ) -> list[dict]:

    tasks = [
        _semantic_match_phrase(p, phrase_vector(p), techniques, threshold)
        for p in phrases
    ]

    results = []
    for chunk in await asyncio.gather(*tasks):
        results.extend(chunk)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

# ============================================================
# STAGE-1 DYNAMIC TECHNIQUE EXTRACTION
# ============================================================

async def extract_dynamic_techniques(text: str, arg2, arg3=None, limit=25, *_, **__):
    """
    Backward-compatible dynamic technique extraction.

    Supported call styles:
      (text, techniques, behaviors=None, limit=25)

    This prevents silent mis-wiring that causes missing techniques and downstream sparsity.
    """

    # Heuristic: techniques are dicts with "id"/"name"; behaviors are dicts with "text"/"description"
    def looks_like_techniques(x):
        return isinstance(x, list) and (not x or (isinstance(x[0], dict) and ("id" in x[0] or "name" in x[0])))

    def looks_like_behaviors(x):
        return isinstance(x, list) and (not x or (isinstance(x[0], dict) and ("description" in x[0] or "text" in x[0])))

    techniques = None
    behaviors = None

    if looks_like_techniques(arg2):
        techniques = arg2
        behaviors = arg3 if looks_like_behaviors(arg3) else None
    else:
        # old style: arg2=behaviors, arg3=techniques
        behaviors = arg2 if looks_like_behaviors(arg2) else None
        techniques = arg3 if looks_like_techniques(arg3) else None

    techniques = techniques or []
    behaviors = behaviors or []

    print(f"[LING] techniques_in={len(techniques)} behaviors_in={len(behaviors)}")

    behavior_text = ""
    if behaviors:
        behavior_text = "\n".join(
            (b.get("sentence") or b.get("description") or b.get("text") or "")
            for b in behaviors
            if isinstance(b, dict)
        )

    if not behavior_text.strip():
        behavior_text = text

    phrases = extract_candidate_phrases(behavior_text)
    print(f"[LING] candidate phrases extracted: {len(phrases)}")

    matches = await semantic_match_techniques(phrases, techniques)
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
                "evidence": [m["phrase"]],
            })
        if len(out) >= limit:
            break

    out = [t for t in out if t["confidence"] >= 0.18]
    return out

def _sentencize(text: str) -> list[str]:
    doc = nlp(text or "")
    return [s.text.strip() for s in doc.sents if s.text.strip()]

def _best_sentence_for_behavior(behavior: dict, sentences: list[str]) -> str | None:
    btxt = (
        behavior.get("description")
        or behavior.get("text")
        or ""
    ).lower()

    if not btxt:
        return None

    b_tokens = {t.text.lower() for t in nlp(btxt) if t.is_alpha}
    best, score = None, 0

    for s in sentences:
        s_tokens = {t.text.lower() for t in nlp(s) if t.is_alpha}
        overlap = len(b_tokens & s_tokens)
        if overlap > score:
            best, score = s, overlap

    return best if score >= 2 else None
