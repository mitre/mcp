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
from utilities.cti_linguistics import normalize_behavior_text, canonicalize_relationship_endpoints


# ============================================================
# NLP MODEL (GLOBAL, SINGLE LOAD)
# ============================================================

nlp = spacy.load("en_core_web_lg")


# ============================================================
# VECTOR CACHE (PERFORMANCE CRITICAL)
# ============================================================

@lru_cache(maxsize=4096)
def vectorize(text: str):
    return nlp(text).vector


# ============================================================
# RELATIONSHIP CLASSES (OBSERVED VERBS ONLY)
# ============================================================

RELATIONSHIP_CLASSES = {
    "uses", "deploys", "drops", "executes", "installs", "loads",
    "runs", "communicates-with", "associated-with",
    "exfiltrates", "encrypts", "scans", "collects", "harvests",
    "enumerates", "moves", "infiltrates", "injects", "escalates",
}

MIN_REL_CONFIDENCE = 0.6
REL_REJECTIONS: list[dict] = []


# ============================================================
# WORDNET SUPPORT (CLASSIFICATION ONLY)
# ============================================================

WN_MAP = {}
for cls in RELATIONSHIP_CLASSES:
    syns = wn.synsets(cls, pos=wn.VERB)
    WN_MAP[cls] = {
        l.name().replace("_", " ")
        for s in syns
        for l in s.lemmas()
    }

REL_CLASS_VECS = {c: vectorize(c) for c in RELATIONSHIP_CLASSES}


# ============================================================
# INTENT PROTOTYPES (SEMANTIC ANCHORS)
# ============================================================

def _wn_expand(anchors: list[str]) -> str:
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

    return best_intent if best_score >= 0.6 else None


# ============================================================
# ENTITY ROLE INFERENCE (IR-GROUNDED)
# ============================================================

def infer_entity_roles(entity_name: str, ir: dict) -> set[str]:
    roles = set()
    if not entity_name:
        return roles

    name_l = entity_name.lower()

    for group, role in (
        ("threat_actors", "actor"),
        ("malware", "malware"),
        ("tools", "tool"),
        ("infrastructure", "infrastructure"),
        ("data", "data"),
    ):
        for ent in ir.get(group, []):
            if ent.get("name","").lower() == name_l:
                roles.add(role)

    return roles


# ============================================================
# BEHAVIOR NORMALIZATION + QUALIFICATION
# ============================================================

def qualify_behaviors(behaviors: list[dict]) -> list[dict]:
    qualified = []

    for b in behaviors:
        text = b.get("text") or b.get("description")
        if not text:
            continue

        doc = nlp(text)

        if not any(t.pos_ == "VERB" for t in doc):
            continue
        if not any(t.dep_ in ("dobj", "pobj") for t in doc):
            continue
        if any(t.text.lower() in {"we", "researchers", "analysts"} for t in doc):
            continue

        qualified.append(b)

    return qualified


def normalize_and_qualify_behaviors(ir: dict) -> tuple[list[dict], list[dict]]:
    raw = ir.get("behaviors", [])
    normalized = []

    for b in raw:
        if not isinstance(b, dict):
            continue

        text = b.get("text") or b.get("description")
        if not text:
            continue

        norm = normalize_behavior_text(text)
        if not norm:
            continue

        bb = dict(b)
        bb["text"] = norm
        bb["description"] = norm
        bb.setdefault("confidence", 0.6)
        bb.setdefault("source", "nlp")

        normalized.append(bb)

    qualified = qualify_behaviors(normalized)

    print(
        f"[BEH] raw={len(raw)} "
        f"normalized={len(normalized)} "
        f"qualified={len(qualified)}"
    )

    if raw and not qualified:
        print("[BEH][WARN] ALL behaviors rejected — sample raw:")
        for b in raw[:3]:
            print("   •", b.get("text") or b.get("description"))

    return normalized, qualified


# ============================================================
# RELATIONSHIP CLASS MATCHING
# ============================================================

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
        if cosine_sim(v_vec, c_vec) >= 0.65:
            return cls

    return None


# ============================================================
# ADMISSIBILITY + CONFIDENCE
# ============================================================

def relationship_allowed(src_roles, verb, tgt_roles, rel_class=None, explicit_joint=False):
    if not src_roles:
        src_roles = {"actor"}
    if tgt_roles == {"unknown"}:
        return True

    intent = infer_relationship_intent(rel_class or verb)
    if not intent:
        return False

    if intent == "associate":
        return True
    if "actor" in src_roles:
        return True
    if "tool" in src_roles and "tool" in tgt_roles and intent == "use":
        return explicit_joint

    src_is_tool = bool(src_roles & {"tool", "malware"})
    if intent in {"use", "exfiltrate", "communicate", "privilege"}:
        return src_is_tool

    return False


def score_relationship(src, rel, tgt, sentence, source_context):
    score = 0.25
    sent = (sentence or "").lower()

    if tgt == "<unspecified>":
        return 0.45

    if source_context == "behavior":
        score += 0.10
    elif source_context == "sentence":
        score += 0.05
    elif source_context == "llm":
        score -= 0.10

    if src.lower() in sent and tgt.lower() in sent:
        score += 0.35

    intent = infer_relationship_intent(rel)
    if intent:
        sim = cosine_sim(vectorize(rel), INTENT_PROTOTYPES[intent])
        if sim > 0.5:
            score += min(sim * 0.3, 0.25)

    if sentence and len(sentence.split()) >= 10:
        score += 0.10

    if intent == "associate":
        score = min(score, 0.75)

    return min(round(score, 2), 0.95)


# ============================================================
# CORE EXTRACTION (SINGLE AUTHORITY)
# ============================================================

def _extract_relationships_from_doc(doc, ir, source_label):
    results = []

    for tok in doc:
        rel_class = match_relationship_class(tok)
        if not rel_class:
            continue

        sentence = tok.sent.text
        sentence_l = sentence.lower()

        sources = [
            ent["name"]
            for g in ("threat_actors", "malware", "tools")
            for ent in ir.get(g, [])
            if ent.get("name") and ent["name"].lower() in sentence_l
        ]

        if not sources and ir.get("threat_actors"):
            sources = [ir["threat_actors"][0]["name"]]

        if not sources:
            continue

        targets = [
            ent["name"]
            for g in ("malware", "tools", "infrastructure")
            for ent in ir.get(g, [])
            if ent.get("name") and ent["name"].lower() in sentence_l
        ]

        if not targets:
            intent = infer_relationship_intent(tok.lemma_)
            if intent == "exfiltrate":
                targets = ["<data>"]
            elif intent == "communicate":
                targets = ["<infrastructure>"]

        for src in sources:
            src_roles = infer_entity_roles(src, ir)
            for tgt in targets:
                tgt_roles = infer_entity_roles(tgt, ir) or {"unknown"}

                if not relationship_allowed(
                    src_roles,
                    tok.lemma_.lower(),
                    tgt_roles,
                    rel_class=rel_class,
                    explicit_joint=(src.lower() in sentence_l and tgt.lower() in sentence_l)
                ):
                    continue

                conf = score_relationship(src, rel_class, tgt, sentence, source_label)
                if conf < MIN_REL_CONFIDENCE:
                    continue

                results.append({
                    "source": src,
                    "relationship": rel_class,
                    "target": tgt,
                    "confidence": conf,
                    "evidence": sentence,
                    "source_context": source_label,
                })

    return results


# ============================================================
# PUBLIC APIs
# ============================================================

async def semantic_relationships(text: str, ir: dict) -> list[dict]:
    MAX_CHARS = int(nlp.max_length * 0.8)
    results = []

    for i in range(0, len(text), MAX_CHARS):
        doc = nlp(text[i:i + MAX_CHARS])
        results.extend(_extract_relationships_from_doc(doc, ir, "sentence"))

    print(f"[REL] semantic={len(results)}")
    return results


def relationships_from_behaviors(behaviors, ir):
    results = []
    for b in behaviors:
        text = b.get("description") or b.get("text")
        if not text:
            continue
        doc = nlp(text)
        results.extend(_extract_relationships_from_doc(doc, ir, "behavior"))

    print(f"[REL] behavior={len(results)}")
    return results


async def extract_all_relationships(text, ir, qualified):
    """
    Single authority aggregator.
    Runs relationship extraction on QUALIFIED behaviors only,
    canonicalizes endpoints, then dedupes with evidence hygiene.
    """

    rel_text = "\n".join(
        (b.get("description") or b.get("text") or "").strip()
        for b in qualified
        if isinstance(b, dict)
    ).strip()

    rel_sem = await semantic_relationships(rel_text, ir) if rel_text else []
    rel_beh = relationships_from_behaviors(qualified, ir) if qualified else []

    combined = canonicalize_relationship_endpoints(ir, rel_sem + rel_beh)

    print(
        f"[REL] semantic={len(rel_sem)} "
        f"behavior={len(rel_beh)} "
        f"combined_pre_dedup={len(combined)}"
    )

    deduped = dedup_relationships(combined)
    print(f"[REL] final_deduped={len(deduped)}")
    return deduped


def dedup_relationships(rels: list[dict]) -> list[dict]:
    """
    Deduplicate by (source, relationship, target).
    Merges evidence into a set and slightly boosts confidence on independent corroboration.
    """
    dedup: dict[tuple[str, str, str], dict] = {}

    for r in rels or []:
        src = r.get("source")
        rel = r.get("relationship")
        tgt = r.get("target")
        if not (src and rel and tgt):
            continue

        key = (src, rel, tgt)
        ev = r.get("evidence")

        if key not in dedup:
            rr = dict(r)
            rr["evidence"] = {ev} if ev else set()
            dedup[key] = rr
            continue

        if ev and ev not in dedup[key]["evidence"]:
            dedup[key]["evidence"].add(ev)
            try:
                dedup[key]["confidence"] = min(float(dedup[key].get("confidence", 0.0)) + 0.05, 0.95)
            except Exception:
                pass

    # convert evidence set back to list to keep JSON-safe behavior later
    out = []
    for v in dedup.values():
        vv = dict(v)
        if isinstance(vv.get("evidence"), set):
            vv["evidence"] = sorted(vv["evidence"])
        out.append(vv)

    return out

# ============================================================
# THREAT ACTOR INFERENCE
# ============================================================

def infer_threat_actors(ir: dict) -> list[dict]:
    if not ir.get("relationships"):
        return []

    malicious = {
        e["name"].lower()
        for g in ("malware", "tools", "infrastructure")
        for e in ir.get(g, [])
        if e.get("name")
    }

    sources = {
        r["source"].lower()
        for r in ir["relationships"]
        if r["target"].lower() in malicious
    }

    return [
        a for a in ir.get("threat_actors", [])
        if a.get("name","").lower() in sources
    ]
