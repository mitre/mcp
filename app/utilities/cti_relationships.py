"""
cti_relationships.py — Unified Relationship Extraction

This module:
    • Extracts semantic relationships from text (spaCy)
    • Normalizes LLM free-text relationships
    • Returns list of {source, relationship, target}
"""

import spacy, re, asyncio
from nltk.corpus import wordnet as wn
from utilities.cti_mitre_extract import cosine_sim
from utilities.cti_parsing import ollama_generate_async


# Load spaCy model
nlp = spacy.load("en_core_web_lg")

# -------------------------------------------------------------------
# Dynamic Canonical Verb System
# -------------------------------------------------------------------

LLM_CANON_PROMPT = """
    Map the verb below to the closest CTI canonical action verb.
    Allowed verbs:
    uses, deploys, drops, executes, loads,
    communicates-with, associated-with, exfiltrates, encrypts,
    installs, runs, scans, enumerates, injects, moves, harvests.

    Return ONLY one verb from this list.

    Verb: "{{}}"
    """

BASE_CANONICAL = {
    "uses", "deploys", "drops", "executes", "installs", "loads",
    "leverages", "launches", "runs", "communicates-with", "associated-with",
    "exfiltrates", "encrypts", "scans", "collects", "harvests",
    "enumerates", "moves", "infiltrates", "injects", "escalates"
}



def expand_canonical_from_ir(ir):
    """Dynamically add verbs found in behaviors, summaries, sentences."""
    extras = set()
    for b in ir.get("behaviors", []):
        text = b.get("text") or b.get("description") or ""
        for tok in nlp(text):
            if tok.pos_ == "VERB":
                extras.add(tok.lemma_.lower())
    return extras

def build_canonical(ir):
    dynamic = expand_canonical_from_ir(ir)
    canonical = BASE_CANONICAL | dynamic
    return {c: nlp(c).vector for c in canonical}

DEBUG_REL = True

def rel_debug(msg):
    if DEBUG_REL:
        print(f"[REL-DBG] {msg}")

# -------------------------------------------------------------------
# WordNet synonym clusters for BASE_CANONICAL
# -------------------------------------------------------------------

WN_MAP = {}
for c in BASE_CANONICAL:                     # <-- FIXED (not CANONICAL)
    syns = wn.synsets(c, pos=wn.VERB)
    WN_MAP[c] = set(
        [l.name().replace('_',' ') for s in syns for l in s.lemmas()]
    )

# -------------------------------------------------------------------
# Precompute initial canonical vectors (will be replaced dynamically later)
# -------------------------------------------------------------------

CANON_VECS = {c: nlp(c).vector for c in BASE_CANONICAL}   # <-- FIXED

# -------------------------------------------------------------------
# Regex relationship patterns
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# Dynamic regex patterns derived from canonical verbs
# -------------------------------------------------------------------

def build_dynamic_patterns():
    """
    Generate regex rules dynamically from canonical verbs.
    Example phrases captured:
        '<Entity> uses <Entity>'
        '<Entity> used by <Entity>'
        '<Entity> is used by <Entity>'
        '<Entity> associated with <Entity>'
    """
    patterns = []

    # HIGH-LEVEL ENTITY REGEX (same as before)
    ENT = r"([A-Z][\w\s-]{1,50})"

    # use BASE_CANONICAL so it honors the verbs you already maintain
    for verb in BASE_CANONICAL:

        # root verb form (e.g. "uses")
        v = verb

        # generate common conjugations automatically
        past = v + "d" if not v.endswith("e") else v + "d"  # simple past heuristic
        gerund = v + "ing"

        # active voice: "X uses Y"
        patterns.append((rf"{ENT}\s+{v}\s+{ENT}", v))

        # passive: "X is used by Y"
        patterns.append((rf"{ENT}\s+is\s+{past}\s+by\s+{ENT}", v))

        # passive: "X was used by Y"
        patterns.append((rf"{ENT}\s+was\s+{past}\s+by\s+{ENT}", v))

        # passive gerund: "X is being used by Y"
        patterns.append((rf"{ENT}\s+is\s+being\s+{past}\s+by\s+{ENT}", v))

        # linked/associated variants for association verbs
        if v in ("associated-with", "communicates-with"):
            patterns.append((rf"{ENT}\s+associated\s+with\s+{ENT}", v))
            patterns.append((rf"{ENT}\s+linked\s+to\s+{ENT}", v))

    return patterns

PATTERNS = build_dynamic_patterns()


# -------------------------------------------------------------------
# Dynamic verb clustering
# -------------------------------------------------------------------

def dynamic_verb_map(doc):
    verbs = list({t.lemma_.lower() for t in doc if t.pos_ == "VERB"})
    if not verbs:
        return {}
    docs = {v: nlp(v).vector for v in verbs}
    threshold = 0.78
    used = set()
    clusters = []
    for v in verbs:
        if v in used:
            continue
        group = {v}
        used.add(v)
        for o in verbs:
            if cosine_sim(docs[v], docs[o]) >= threshold:
                group.add(o)
                used.add(o)
        clusters.append(group)
    cmap = {}
    for g in clusters:
        canon = sorted(g)[0]
        for v in g:
            cmap[v] = canon
    return cmap

# -------------------------------------------------------------------
# Semantic Relationship Extraction
# -------------------------------------------------------------------

def semantic_relationships(text, ir):
    global CANON_VECS                    # <-- FIXED
    print("[REL-SEM] starting semantic_relationships()")
    print(f"[REL-SEM] entities: "
          f"actors={len(ir.get('threat_actors', []))} "
          f"malware={len(ir.get('malware', []))} "
          f"tools={len(ir.get('tools', []))} "
          f"infra={len(ir.get('infrastructure', []))}")
    
    doc = nlp(text)

    # dynamically rebuild canonical vector map
    CANON_VECS = build_canonical(ir)

    cmap = dynamic_verb_map(doc)
    results = []

    for t in doc:
        if t.pos_ != "VERB":
            continue

        raw = cmap.get(t.lemma_.lower())
        print(f"[REL-SEM] processing verb: {t.text} → mapped to {raw}")
        if not raw:
            continue
        if raw:
            rel_type = canonicalize_verb(raw)
        if not rel_type:
            continue

        subj, obj = None, None

        for c in t.children:

            # Active: Exmatter uses SFTP
            if c.dep_ in ("nsubj"):
                subj = " ".join(tok.text for tok in c.subtree)

            # Passive: “was used by BlackMatter”
            if c.dep_ in ("nsubjpass"):
                obj = " ".join(tok.text for tok in c.subtree)

            # Object
            if c.dep_ in ("dobj", "pobj", "attr", "oprd"):
                obj = " ".join(tok.text for tok in c.subtree)

            # Agent phrase: “by BlackMatter”
            if c.dep_ == "agent":
                subj = " ".join(tok.text for tok in c.subtree)


        if subj and obj:
            if not subj or not obj:
                continue
            src = resolve_entity(best_entity_match(subj, ir), ir)
            tgt = resolve_entity(best_entity_match(obj, ir), ir)

            if src and tgt and src != tgt:
                results.append({
                    "source": src,
                    "relationship": rel_type,
                    "target": tgt,
                })

    print(f"[REL-SEM] produced {len(results)} relationships")
    if results:
        print("[REL-SEM] sample:", results[:5])
    return results

# -------------------------------------------------------------------
# LLM → normalized CTI relationships
# -------------------------------------------------------------------

def normalize_llm_relationships(llm_rels, ir):
    out = []

    for r in llm_rels:

        # dict-style relationships
        if isinstance(r, dict):

            src = r.get("source") or r.get("actor") or r.get("malware")
            tgt = r.get("target") or r.get("tool") or r.get("infrastructure")
            rel = r.get("relationship") or r.get("type")

            if not (src and tgt and rel):
                continue

            src_fixed = resolve_entity(src, ir)
            tgt_fixed = resolve_entity(tgt, ir)

            if src_fixed and tgt_fixed and src_fixed != tgt_fixed:
                out.append({
                    "source": src_fixed,
                    "relationship": canonicalize_verb(rel.lower().replace(" ", "-")),
                    "target": tgt_fixed
                })

        # free-text relationships
        doc = nlp(str(r))
        root = None
        for t in doc:
            if t.dep_ == "ROOT" and t.pos_ == "VERB":
                root = t
                break
        if not root:
            continue

        subj, obj = None, None
        for c in root.children:
            if c.dep_ in ("nsubj", "nsubjpass"):
                subj = " ".join([tok.text for tok in c.subtree])
            if c.dep_ in ("dobj", "pobj", "attr", "oprd"):
                obj_tokens = [tok.text for tok in c.subtree if tok.pos_ in ("NOUN", "PROPN")]
                obj = " ".join(obj_tokens)

        if not (subj and obj):
            continue

        src = resolve_entity(subj, ir)
        tgt = resolve_entity(obj, ir)

        if src and tgt and src != tgt:
            canon = canonicalize_verb(root.lemma_.lower().strip())
            out.append({
                "source": src,
                "relationship": canon,
                "target": tgt,
            })

    return out

# -------------------------------------------------------------------
# Verb Canonicalization
# -------------------------------------------------------------------

async def canonicalize_verb_async(verb: str) -> str:
    """
    Use the existing Stage-1 Ollama LLM canonicalizer.
    The model maps verbs to the approved CTI verb set.
    """
    prompt = LLM_CANON_PROMPT.format(verb)

    try:
        response = await ollama_generate_async(prompt)
        if not response:
            return None

        # First word only, strip punctuation/newlines
        return response.strip().split()[0]
    except Exception:
        return None


def canonicalize_verb(verb: str) -> str:
    """
    ALWAYS canonicalize via LLM, even if semantic resolution fails.
    """
    try:
        # force async usage for *all* verbs
        return asyncio.run(canonicalize_verb_async(verb))
    except RuntimeError:
        # fallback if inside existing event loop
        return verb.lower().strip()


# -------------------------------------------------------------------
# Entity Resolution Helpers
# -------------------------------------------------------------------

def resolve_entity(token_text, ir):
    if not token_text:
        return None
    t = token_text.lower().strip()
    t = t.replace("-", " ").replace("_", " ")
    if len(t) <= 2:
        return None

    for group in ("threat_actors", "malware", "tools", "infrastructure"):
        for ent in ir.get(group, []):
            name_field = ent.get("name")
            if not name_field:
                continue

            name = name_field.lower().replace("-", " ").replace("_", " ")
            if t in name or name in t:
                return ent["name"]

    return None

def repair_llm_relationship_dicts(llm_rels, ir):
    cleaned = []
    for r in llm_rels:
        if not isinstance(r, dict):
            continue

        src = r.get("source") or r.get("actor") or r.get("malware") or r.get("tool")
        tgt = r.get("target") or r.get("tool")
        rel = r.get("relationship") or r.get("type")

        if not (src and tgt and rel):
            continue

        src_fixed = resolve_entity(src, ir)
        tgt_fixed = resolve_entity(tgt, ir)

        if src_fixed and tgt_fixed and src_fixed != tgt_fixed:
            cleaned.append({
                "source": src_fixed,
                "relationship": canonicalize_verb(rel.lower()),
                "target": tgt_fixed
            })
    return cleaned

# -------------------------------------------------------------------
# Regex Pattern-Based Relationships
# -------------------------------------------------------------------

def pattern_based_relationships(text, ir):
    results = []
    for pattern, rel in PATTERNS:
        for m in re.findall(pattern, text, flags=re.I):
            src = resolve_entity(m[0], ir)
            tgt = resolve_entity(m[1], ir)
            if src and tgt and src != tgt:
                results.append({
                    "source": src,
                    "relationship": rel,
                    "target": tgt
                })
    print(f"[REL-PAT] produced {len(results)} relationships")
    if results:
        print("[REL-PAT] sample:", results[:5])
    return results

# -------------------------------------------------------------------
# Utility: Fix mixed/strange relationship dict formats
# -------------------------------------------------------------------

def repair_mixed_relationship_formats(rel_list):
    repaired = []

    for r in rel_list:
        if "source" in r and "target" in r:
            repaired.append(r)
            continue

        if "actor" in r and "tool" in r:
            repaired.append({
                "source": r["actor"],
                "relationship": canonicalize_verb(r.get("type", "").lower()),
                "target": r["tool"]
            })
            continue

        if "tool" in r and "technique" in r:
            repaired.append({
                "source": r["tool"],
                "relationship": r.get("type", "").lower().replace(" ", "-"),
                "target": r["technique"]
            })
            continue

        if "tool" in r and "related_tools" in r:
            for tgt in r["related_tools"]:
                repaired.append({
                    "source": r["tool"],
                    "relationship": r.get("type", "").lower().replace(" ", "-"),
                    "target": tgt
                })
            continue

    return repaired

# -------------------------------------------------------------------
# Entity matching heuristic
# -------------------------------------------------------------------

def best_entity_match(phrase, ir):
    text = phrase.lower()

    candidates = []
    for group in ("threat_actors", "malware", "tools", "infrastructure"):
        for ent in ir.get(group, []):
            name = ent.get("name", "").lower()
            if name and name in text:
                candidates.append(ent["name"])

            for alias in ent.get("aliases", []):
                alias_l = alias.lower()
                if alias_l and alias_l in text:
                    candidates.append(ent["name"])

    if candidates:
        return candidates[0]

    return None

