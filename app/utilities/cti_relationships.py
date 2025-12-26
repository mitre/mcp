"""
cti_relationships.py — Unified Relationship Extraction & Classification

AUTHORITATIVE relationship logic for Stage 1 and Stage 2.

Key guarantees:
- Verbs are ONLY taken from observed text (never invented)
- One internal extraction path
- Deterministic role + direction enforcement
- Mandatory confidence and evidence
- Backward compatible with cti_pipeline_stage1.py
"""

import spacy
from functools import lru_cache
from nltk.corpus import wordnet as wn
from utilities.cti_mitre_extract import cosine_sim
from utilities.cti_parsing import ollama_generate_async

# -------------------------------------------------------------------
# NLP model (global, single load)
# -------------------------------------------------------------------

nlp = spacy.load("en_core_web_lg")

# -------------------------------------------------------------------
# Vector cache (MAJOR speed win)
# -------------------------------------------------------------------

@lru_cache(maxsize=4096)
def vectorize(text: str):
    return nlp(text).vector

# -------------------------------------------------------------------
# Relationship Classes (semantic labels, NOT injected verbs)
# -------------------------------------------------------------------

RELATIONSHIP_CLASSES = {
    "uses", "deploys", "drops", "executes", "installs", "loads",
    "runs", "communicates-with", "associated-with",
    "exfiltrates", "encrypts", "scans", "collects", "harvests",
    "enumerates", "moves", "infiltrates", "injects", "escalates"
}

MIN_REL_CONFIDENCE = 0.7
DEBUG_REL = False
REL_REJECTIONS = []

def rel_debug(msg: str):
    if DEBUG_REL:
        print(f"[REL-DBG] {msg}")

# -------------------------------------------------------------------
# WordNet synonym support (classification only)
# -------------------------------------------------------------------

WN_MAP = {}
for cls in RELATIONSHIP_CLASSES:
    syns = wn.synsets(cls, pos=wn.VERB)
    WN_MAP[cls] = {
        l.name().replace("_", " ")
        for s in syns
        for l in s.lemmas()
    }

REL_CLASS_VECS = {c: vectorize(c) for c in RELATIONSHIP_CLASSES}

# -------------------------------------------------------------------
# Intent prototypes (dynamic semantic anchors)
# -------------------------------------------------------------------

def _wn_expand(anchors: list[str]) -> str:
    """
    Expand anchor verbs with WordNet synonyms.
    Deterministic and bounded.
    """
    out = set()
    for w in anchors:
        out.add(w)
        for syn in wn.synsets(w, pos=wn.VERB):
            for lemma in syn.lemmas():
                out.add(lemma.name().replace("_", " "))
    return " ".join(sorted(out)[:80])

INTENT_ANCHORS = {
    "use":        ["use", "employ", "leverage", "utilize", "run", "execute"],
    "exfiltrate": ["exfiltrate", "steal", "siphon", "transfer", "export"],
    "communicate":["communicate", "connect", "beacon", "contact"],
    "privilege":  ["inject", "escalate"],
    "associate":  ["associate", "attribute", "link", "relate"],
}

INTENT_PROTOTYPES = {
    k: vectorize(_wn_expand(v))
    for k, v in INTENT_ANCHORS.items()
}

def infer_relationship_intent(verb_lemma: str) -> str | None:
    v_vec = vectorize(verb_lemma)
    best_intent, best_score = None, 0.0

    for intent, proto_vec in INTENT_PROTOTYPES.items():
        score = cosine_sim(v_vec, proto_vec)
        if score > best_score:
            best_intent, best_score = intent, score

    return best_intent if best_score >= 0.7 else None

# -------------------------------------------------------------------
# Entity role inference (IR-grounded only)
# -------------------------------------------------------------------

def infer_entity_roles(entity_name: str, ir: dict) -> set[str]:
    roles = set()
    if not entity_name:
        return roles

    entity_norm = entity_name.lower()

    for group, role in (
        ("threat_actors", "actor"),
        ("malware", "malware"),
        ("tools", "tool"),
        ("infrastructure", "infrastructure"),
        ("data", "data"),
    ):
        for ent in ir.get(group, []):
            canon = ent.get("canonical", "").lower()
            name  = ent.get("name", "").lower()
            if entity_norm in {canon, name}:
                roles.add(role)

    return roles

# -------------------------------------------------------------------
# Analyst-style admissibility gating (STRUCTURAL, NON-BRITTLE)
# -------------------------------------------------------------------

def relationship_allowed(
        src_roles: set,
        verb_lemma: str,
        tgt_roles: set,
        rel_class: str | None = None,
        explicit_joint: bool = False,
    ) -> bool:
    if not src_roles:
        return False

    intent = infer_relationship_intent(rel_class or verb_lemma)
    if not intent:
        return False

    # Analyst rule: attribution / association always admissible
    if intent == "associate":
        return True

    # Analyst rule: actors may act on weakly-typed targets
    if "actor" in src_roles:
        return True

    # Tool↔tool usage requires explicit joint mention
    if "tool" in src_roles and "tool" in tgt_roles and intent == "use":
        return explicit_joint

    src_is_tool = bool(src_roles & {"tool","malware"})
    tgt_is_tool = "tool" in tgt_roles
    tgt_is_mal  = "malware" in tgt_roles
    tgt_is_inf  = "infrastructure" in tgt_roles

    if intent == "use":
        return src_is_tool and (tgt_is_tool or tgt_is_mal or tgt_is_inf)

    if intent == "exfiltrate":
        return src_is_tool

    if intent == "communicate":
        return src_is_tool

    if intent == "privilege":
        return src_is_tool

    return False

# -------------------------------------------------------------------
# Confidence scoring (dynamic, intent-driven)
# -------------------------------------------------------------------

def score_relationship(src: str, rel: str, tgt: str, sentence: str) -> float:
    """
    Deterministic confidence scoring using:
    - structural evidence
    - semantic intent strength (vector-based)
    """
    score = 0.25
    sent = (sentence or "").lower()

    # Structural evidence: both endpoints present
    if src and tgt and src.lower() in sent and tgt.lower() in sent:
        score += 0.35

    # Semantic strength via intent similarity
    intent = infer_relationship_intent(rel)
    if intent:
        proto_vec = INTENT_PROTOTYPES.get(intent)
        if proto_vec is not None:
            sim = cosine_sim(vectorize(rel), proto_vec)
            if sim > 0.5:
                score += min(sim * 0.3, 0.25)

    # Longer sentences reduce fragment noise
    if sentence and len(sentence.split()) >= 10:
        score += 0.10

    # Association is epistemically weaker
    if intent == "associate":
        score = min(score, 0.75)

    return min(round(score, 2), 0.95)

# -------------------------------------------------------------------
# Verb → relationship class (OBSERVED VERBS ONLY)
# -------------------------------------------------------------------

def match_relationship_class(token) -> str | None:
    if token.pos_ != "VERB":
        return None

    lemma = token.lemma_.lower()
    if not lemma.isalpha() or len(lemma) < 3:
        return None
    if token.tag_ in ("MD", "AUX"):
        return None

    if lemma in RELATIONSHIP_CLASSES:
        return lemma

    for cls, syns in WN_MAP.items():
        if lemma in syns:
            return cls

    v_vec = vectorize(lemma)
    for cls, c_vec in REL_CLASS_VECS.items():
        if cosine_sim(v_vec, c_vec) >= 0.75:
            return cls

    return None

# -------------------------------------------------------------------
# Optional LLM tie-breaker (async, NEVER primary)
# -------------------------------------------------------------------

async def canonicalize_verb_llm(verb: str) -> str | None:
    prompt = f"""
Map the verb below to the closest CTI relationship class.
Allowed classes:
{", ".join(sorted(RELATIONSHIP_CLASSES))}

Return ONLY one class.

Verb: "{verb}"
"""
    try:
        response = await ollama_generate_async(prompt)
        if response:
            cls = response.strip().split()[0]
            if cls in RELATIONSHIP_CLASSES:
                return cls
    except Exception:
        pass
    return None

async def canonicalize_verb(verb: str) -> str | None:
    return await canonicalize_verb_llm(verb)

# -------------------------------------------------------------------
# INTERNAL UNIFIED EXTRACTION PATH (SINGLE AUTHORITY)
# -------------------------------------------------------------------

async def _extract_relationships_from_doc(doc, ir: dict, source_label: str) -> list[dict]:
    results = []

    for tok in doc:
        rel_class = match_relationship_class(tok)
        if not rel_class:
            continue

        sentence = tok.sent.text
        sentence_l = sentence.lower()

        candidate_sources = [
            ent["name"]
            for g in ("threat_actors", "malware", "tools")
            for ent in ir.get(g, [])
            if ent.get("name","").lower() in sentence_l
        ]
        if not candidate_sources:
            for c in tok.children:
                if c.dep_ in ("nsubj", "nsubjpass", "agent"):
                    src = resolve_entity(c.text.lower(), ir)
                    if src:
                        candidate_sources = [src]
                        break
                
        candidate_targets = [
            ent["name"]
            for g in ("malware", "tools", "infrastructure")
            for ent in ir.get(g, [])
            if ent.get("name","").lower() in sentence_l
        ]
        # --------------------------------------------------
        # Target resolution (ordered, non-duplicative)
        # --------------------------------------------------
        if not candidate_targets:
            # 1️⃣ Try object-based resolution (real entities first)
            obj = tok.text.lower()
            tgt = resolve_entity(obj, ir)
            if tgt:
                candidate_targets = [tgt]

        # 2️⃣ Final fallback: intent-based synthetic targets
        if not candidate_targets:
            intent = infer_relationship_intent(tok.lemma_)
            if intent == "exfiltrate":
                candidate_targets = [{"name": "<data>", "role": "data"}]
            elif intent == "communicate":
                candidate_targets = [{"name": "<infrastructure>", "role": "infrastructure"}]


        for src in candidate_sources:
            src_roles = infer_entity_roles(src, ir)

            for tgt in candidate_targets:
                if isinstance(tgt, dict):
                    tgt_name = tgt["name"]
                    tgt_roles = {tgt["role"]}
                else:
                    tgt_name = tgt
                    tgt_roles = infer_entity_roles(tgt, ir)

                if not tgt_name or src == tgt_name:
                    continue

                explicit_joint = (
                    src.lower() in sentence_l and tgt_name.lower() in sentence_l
                )

                if not relationship_allowed(
                    src_roles,
                    tok.lemma_.lower(),
                    tgt_roles,
                    rel_class=rel_class,
                    explicit_joint=explicit_joint,
                ):
                    REL_REJECTIONS.append({
                        "reason": "relationship_allowed_failed",
                        "source": src,
                        "verb": tok.lemma_,
                        "rel_class": rel_class,
                        "target": tgt_name,
                        "evidence": sentence,
                        "source_context": source_label,
                    })
                    continue

                conf = score_relationship(src, rel_class, tgt_name, sentence)
                min_conf = 0.5 if rel_class == "associated-with" else MIN_REL_CONFIDENCE
                if conf < min_conf:
                    REL_REJECTIONS.append({
                        "reason": "below_min_confidence",
                        "source": src,
                        "verb": tok.lemma_,
                        "rel_class": rel_class,
                        "target": tgt_name,
                        "confidence": conf,
                        "min_required": min_conf,
                        "evidence": sentence,
                        "source_context": source_label,
                    })
                    continue

                results.append({
                    "source": src,
                    "relationship": rel_class,
                    "target": tgt_name,
                    "confidence": conf,
                    "evidence": sentence,
                    "source_context": source_label,
                })

    return results

# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

async def semantic_relationships(text: str, ir: dict) -> list[dict]:
    doc = nlp(text)
    return await _extract_relationships_from_doc(doc, ir, "sentence")

def relationships_from_behaviors(behaviors: list, ir: dict) -> list[dict]:
    results = []

    for b in behaviors:
        text = b.get("description")
        if not text:
            continue

        doc = nlp(text)
        for tok in doc:
            rel_class = match_relationship_class(tok)
            if not rel_class:
                continue

            src = resolve_entity(best_entity_match(text, ir), ir)
            tgt = resolve_entity(best_entity_match(text, ir), ir)
            if not src or not tgt or src == tgt:
                continue

            src_roles = infer_entity_roles(src, ir)
            tgt_roles = infer_entity_roles(tgt, ir)

            explicit_joint = (
                src.lower() in text.lower()
                and tgt.lower() in text.lower()
            )

            if not relationship_allowed(
                src_roles,
                tok.lemma_.lower(),
                tgt_roles,
                rel_class=rel_class,
                explicit_joint=explicit_joint,
            ):
                continue

            conf = score_relationship(src, rel_class, tgt, text)

            intent = infer_relationship_intent(rel_class)
            min_conf = 0.5 if intent in {"associate","use"} else MIN_REL_CONFIDENCE
            if conf < min_conf:
                continue

            results.append({
                "source": src,
                "relationship": rel_class,
                "target": tgt,
                "confidence": conf,
                "evidence": text,
                "source_context": "behavior",
            })

    return results

def pattern_based_relationships(text: str, ir: dict) -> list[dict]:
    return []

async def normalize_llm_relationships(llm_rels: list, ir: dict) -> list[dict]:
    out = []
    for r in llm_rels:
        if not isinstance(r, dict):
            continue

        src = r.get("source") or r.get("actor") or r.get("malware")
        tgt = r.get("target") or r.get("tool") or r.get("infrastructure")
        rel = r.get("relationship") or r.get("type")
        if not (src and tgt and rel):
            continue

        src_fixed = resolve_entity(src, ir)
        tgt_fixed = resolve_entity(tgt, ir)
        if not src_fixed or not tgt_fixed or src_fixed == tgt_fixed:
            continue

        cls = await canonicalize_verb_llm(rel.lower())
        if not cls:
            continue

        src_roles = infer_entity_roles(src_fixed, ir)
        tgt_roles = infer_entity_roles(tgt_fixed, ir)

        if not relationship_allowed(src_roles, rel.lower(), tgt_roles, rel_class=cls):
            continue

        out.append({
            "source": src_fixed,
            "relationship": cls,
            "target": tgt_fixed,
            "confidence": 0.6,
            "evidence": "llm",
            "source_context": "llm",
        })

    return out

# -------------------------------------------------------------------
# Entity resolution helpers (UNCHANGED)
# -------------------------------------------------------------------

def resolve_entity(token_text: str, ir: dict) -> str | None:
    if not token_text:
        return None

    t = token_text.lower().replace("-", " ").replace("_", " ").strip()
    if len(t) <= 2:
        return None

    for group in ("threat_actors", "malware", "tools", "infrastructure", "data"):
        for ent in ir.get(group, []):
            name = ent.get("name")
            if not name:
                continue
            norm = name.lower().replace("-", " ").replace("_", " ")
            if t in norm or norm in t:
                return name
    return None

def best_entity_match(phrase: str, ir: dict) -> str | None:
    if not phrase or not isinstance(phrase, str):
        return None
    text = phrase.lower().strip()
    for group in ("threat_actors", "malware", "tools", "infrastructure", "data"):
        for ent in ir.get(group, []):
            name = ent.get("name", "").lower()
            if name and name in text:
                return ent["name"]
            for alias in ent.get("aliases", []):
                if alias.lower() in text:
                    return ent["name"]
    return None

def repair_llm_relationship_dicts(llm_rels: list, ir: dict) -> list[dict]:
    """
    Backward-compatibility shim.
    Normalizes mixed or partial LLM relationship outputs into
    {source, relationship, target} dicts without inference.
    """
    cleaned = []
    for r in llm_rels:
        if not isinstance(r, dict):
            continue

        src = (
            r.get("source")
            or r.get("actor")
            or r.get("malware")
            or r.get("tool")
        )
        tgt = (
            r.get("target")
            or r.get("tool")
            or r.get("infrastructure")
        )
        rel = r.get("relationship") or r.get("type")

        if not (src and tgt and rel):
            continue

        src_fixed = resolve_entity(src, ir)
        tgt_fixed = resolve_entity(tgt, ir)

        if src_fixed and tgt_fixed and src_fixed != tgt_fixed:
            cleaned.append({
                "source": src_fixed,
                "relationship": rel,
                "target": tgt_fixed,
            })

    return cleaned
