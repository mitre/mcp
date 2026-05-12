"""
NLP Layer 1 — Behavior Expansion, Actor Cleanup, Canonical Normalization

This module improves the initial IR returned by an LLM by:
    - Extracting dependency-based behaviors
    - Splitting multi-verb behavior chains (enumerates → transmits → exfiltrates)
    - Normalizing and filtering actor names
    - Canonicalizing all entity names
    - Logging steps for traceability

Output conforms to:
    ir["behaviors"] = [ { "text": "...", "source": "nlp-layer1" }, ... ]
    ir["threat_actors"] cleaned + normalized
"""

import spacy
import re
from rapidfuzz import fuzz

nlp = spacy.load("en_core_web_lg")

def _log(msg: str):
    """Simple stdout logger for tee-based debugging."""
    print(f"[DEPNLP] {msg}")

def normalize_phrase(s: str) -> str:
    """Normalize strings into canonical alphanumeric form."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())

# ---------------------------------------------------------------------------
# Behavior extraction helper
# ---------------------------------------------------------------------------

def extract_dependency_behaviors(doc):
    """
    Extract verb-based behaviors from dependency roots.
    Example:
        Sentence: "ExMatter enumerates directories and exfiltrates files"
        Output: ["enumerate directories", "exfiltrate files"]
    """
    behaviors = []
    for sent in doc.sents:
            root = sent.root
            if root.pos_ != "VERB":
                continue

            obj = None
            for child in root.children:
                if child.dep_ in ("dobj", "pobj", "attr", "dative"):
                    obj = child.text
                    break

            if obj:
                behaviors.append(f"{root.lemma_} {obj}")
            else:
                behaviors.append(root.lemma_)

    return behaviors

def split_multi_verb(behavior: str):
    """
    Split chained behaviors such as:
        "enumerates directories, then exfiltrates data"
    Into:
        ["enumerate directories", "exfiltrate data"]
    """
    parts = re.split(r"\b(?:and|then|but|before|after|,)\b", behavior, flags=re.I)
    return [p.strip() for p in parts if len(p.strip()) > 3]

# ---------------------------------------------------------------------------
# Actor normalization
# ---------------------------------------------------------------------------

VALID_ACTOR_CUES = {"group", "apt", "team", "gang", "operator", "raas"}

def is_valid_actor(name: str) -> bool:
    """
    Remove narrative actors such as:
        "Kroll’s Threat Intelligence Team"
    Keep:
        "BlackMatter", "Conti", "Wizard Spider"
    """
    name_l = name.lower()
    if len(name_l.split()) > 5:
        return False
    if any(cue in name_l for cue in VALID_ACTOR_CUES):
        return True
    # if name is short and proper-noun-like, keep it
    return len(name) <= 25 and name.isalpha()

def normalize_actor_name(name: str):
    """Remove possessives and common suffixes."""
    n = re.sub(r"’s|'s$", "", name)
    n = n.replace("operator", "").replace("team", "").strip()
    return n

# ---------------------------------------------------------------------------
# MAIN LAYER 1 PIPELINE
# ---------------------------------------------------------------------------

def clean_ir_nlp_layer1(ir: dict, original_text: str) -> dict:
    """
    Perform deterministic expansion and cleanup on:
        - behaviors
        - actors
        - entity canonical names
    """
    _log("Beginning NLP Layer #1")
    doc = nlp(original_text)

    # ------------------------
    # Behavior Extraction
    # ------------------------
    dep_behaviors = extract_dependency_behaviors(doc)
    expanded = []
    for b in dep_behaviors:
        expanded.extend(split_multi_verb(b))

    # merge with existing behaviors
    existing = []
    for b in ir.get("behaviors", []):
        if isinstance(b, dict):
            existing.append(b.get("text") or b.get("description") or "")
        else:
            existing.append(str(b))

    merged = existing + expanded
    merged = [normalize_behavior_text(m) for m in merged if len(str(m).strip()) > 3]

    # Vector dedupe (must happen BEFORE relationship extraction)
    merged = dedupe_behaviors_by_vector(merged, threshold=0.92)

    # ------------------------
    # Structural Behavior Filtering (Senior-grade)
    # ------------------------
    filtered = []

    for m in merged:
        doc_b = nlp(m)

        # Require at least one VERB
        if not any(t.pos_ == "VERB" for t in doc_b):
            continue

        # Require at least one object/target
        if not any(t.dep_ in ("dobj", "pobj", "attr") for t in doc_b):
            continue

        filtered.append(m)

    ir["behaviors"] = [{"text": m, "source": "nlp-layer1"} for m in filtered]
    _log(f"Behaviors after NLP Layer 1: {len(ir['behaviors'])}")

    # ------------------------
    # Actor Cleanup
    # ------------------------
    actors = ir.get("threat_actors", [])
    cleaned = []
    removed = []

    for a in actors:
        if isinstance(a, dict):
            name = a.get("name", "")
            if not name:
                continue
            if not is_valid_actor(name):
                removed.append(name)
                continue

            a["name"] = normalize_actor_name(name)
            cleaned.append(a)

        elif isinstance(a, str):
            name = a.strip()
            if not name:
                continue
            if not is_valid_actor(name):
                removed.append(name)
                continue

            cleaned.append({
                "name": normalize_actor_name(name),
                "description": "",
                "confidence": 0.5,
                "source": "recovered-string"
            })

    ir["threat_actors"] = cleaned
    _log(f"Actors removed: {removed}")
    _log(f"Actors kept: {[a['name'] for a in cleaned]}")

    # ------------------------
    # Canonicalization
    # ------------------------
    ir["malware"] = _canonicalize_list(ir.get("malware", []))
    ir["tools"] = _canonicalize_list(ir.get("tools", []))
    ir["infrastructure"] = _canonicalize_list(ir.get("infrastructure", []))
    ir["threat_actors"] = _canonicalize_list(ir.get("threat_actors", []))

    _log(
        f"Canonicalized "
        f"{len(ir['malware']) + len(ir['tools']) + len(ir['infrastructure']) + len(ir['threat_actors'])} entities"
    )

    return ir

# ------------------------
# Canonicalization (STRUCTURE-SAFE)
# ------------------------
def _canonicalize_list(items):
    out = []
    for e in items:
        if isinstance(e, dict):
            e["canonical"] = normalize_phrase(e.get("name", ""))
            out.append(e)
        elif isinstance(e, str) and e.strip():
            out.append({
                "name": e.strip(),
                "canonical": normalize_phrase(e),
                "confidence": 0.5,
                "source": "recovered-string"
            })
    return out

def normalize_behavior_text(text: str) -> str:
    if not text:
        return text
    t = text.strip().lower()

    CANON = {
        "tampering with group policy objects": "modify domain policy configuration",
        "tamper with group policy objects": "modify domain policy configuration",
        "weaken organizational security posture": "degrade security controls",
    }

    for k, v in CANON.items():
        if k in t:
            return v
    return t

def _cosine(a, b) -> float:
    na = float((a*a).sum()) ** 0.5
    nb = float((b*b).sum()) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float((a*b).sum() / (na * nb))

def dedupe_behaviors_by_vector(texts: list[str], threshold: float = 0.92) -> list[str]:
    kept: list[tuple[str, any]] = []
    for t in texts:
        v = nlp(t).vector
        merged = False
        for i, (kt, kv) in enumerate(kept):
            if _cosine(v, kv) >= threshold:
                merged = True
                break
        if not merged:
            kept.append((t, v))
    return [t for t, _ in kept]
