"""
cti_relation_extractor.py — Improved Relationship Extraction

Extracts (subject, verb, object) triples from CTI text using spaCy
dependency parsing with three critical improvements over the original:

1. Compound subject resolution: "BlackCat operators" → BlackCat
2. Conjunction splitting: "deployed A, B and C" → 3 relationships
3. Passive voice inversion: "Mimikatz was deployed by X" → X deploys Mimikatz

Then validates each triple against the entity ontology to keep only
grounded relationships.

No ML. No LLM. Pure dependency parse + ontology lookup.
"""

import re
from plugins.mcp.app.utilities.nlp_model import nlp


# ============================================================
# VALID CTI RELATIONSHIP VERBS
# ============================================================

CTI_VERBS = {
    "use", "employ", "deploy", "execute", "exploit", "target",
    "leverage", "utilize", "compromise", "attack", "infect",
    "download", "upload", "exfiltrate", "steal", "harvest",
    "encrypt", "decrypt", "disable", "modify", "delete",
    "create", "install", "inject", "drop", "deliver",
    "propagate", "spread", "scan", "enumerate", "discover",
    "dump", "extract", "collect", "access", "connect",
    "communicate", "transfer", "move", "copy", "archive",
    "compress", "terminate", "stop", "kill", "clear",
    "gain", "establish", "maintain", "achieve", "perform",
    "conduct", "launch", "initiate",
}

# Verbs that indicate analyst narration, not adversary action
REPORTER_VERBS = {
    "report", "describe", "note", "observe", "identify",
    "analyze", "assess", "document", "publish", "state",
    "indicate", "suggest", "reveal", "show", "find",
    "discover", "track", "monitor", "detect", "warn",
    "believe", "confirm", "attribute",
}


# ============================================================
# SUBJECT RESOLUTION
# ============================================================

def _resolve_full_subject(tok):
    """
    Resolve compound noun phrases to get the full subject.
    "BlackCat operators" → "BlackCat operators"
    "APT29 group" → "APT29 group"
    "the malware" → "the malware"
    """
    # Collect compound modifiers and the head
    compounds = []
    for child in tok.children:
        if child.dep_ in ("compound", "amod", "flat", "appos") and child.i < tok.i:
            # Recursively get compounds of compounds
            for subchild in child.children:
                if subchild.dep_ == "compound" and subchild.i < child.i:
                    compounds.append(subchild)
            compounds.append(child)

    if compounds:
        all_tokens = sorted(compounds + [tok], key=lambda t: t.i)
        return " ".join(t.text for t in all_tokens)

    return tok.text


def _resolve_subject_entity(tok, known_entities):
    """
    Given a subject token, find the best matching known entity.

    Strategy:
    1. Check full compound noun phrase against known entities
    2. Check individual compound parts (and their subtrees)
    3. Check the token itself
    4. Walk UP the tree — if subject's head has a known entity nearby
    """
    full = _resolve_full_subject(tok).lower()

    # Check full phrase
    for ent in known_entities:
        if ent in full or full in ent:
            return ent

    # Check compound parts and their subtrees
    for child in tok.children:
        if child.dep_ in ("compound", "flat", "amod", "nmod", "poss"):
            c_lower = child.text.lower()
            for ent in known_entities:
                if ent in c_lower or c_lower in ent:
                    return ent
            # Check subtree of compound
            subtree_text = " ".join(t.text.lower() for t in child.subtree)
            for ent in known_entities:
                if ent in subtree_text:
                    return ent

    # Check token itself
    tok_lower = tok.text.lower()
    for ent in known_entities:
        if ent in tok_lower or tok_lower in ent:
            return ent

    return None


# ============================================================
# OBJECT RESOLUTION (with conjunction splitting)
# ============================================================

def _resolve_objects(tok, known_entities):
    """
    Resolve direct objects including conjunctions.
    "deployed A, B and C" → [A, B, C]

    Returns list of (object_text, matched_entity_or_None)
    """
    objects = []

    # Get the primary object and its conjuncts
    all_objects = [tok] + list(tok.conjuncts)

    for obj_tok in all_objects:
        # Get full noun phrase for this object
        subtree_text = " ".join(t.text for t in obj_tok.subtree
                                if t.dep_ != "cc" and t.text.lower() not in ("and", "or", ","))
        obj_text = subtree_text.strip()

        # Try to match against known entities
        obj_lower = obj_text.lower()
        matched = None
        for ent in known_entities:
            if ent in obj_lower or obj_lower in ent:
                matched = ent
                break

        # If no match on full phrase, try just the head token
        if not matched:
            head_lower = obj_tok.text.lower()
            for ent in known_entities:
                if ent in head_lower or head_lower in ent:
                    matched = ent
                    break

        objects.append((obj_text, matched))

    return objects


# ============================================================
# CORE TRIPLE EXTRACTION
# ============================================================

def extract_triples(text: str, known_entities: set[str]) -> list[dict]:
    """
    Extract (subject, verb, object) triples from CTI text.

    Handles:
    - Active voice: "BlackCat uses Mimikatz"
    - Passive voice: "Mimikatz was deployed by BlackCat"
    - Compound subjects: "BlackCat operators leverage tools"
    - Conjunctions: "deployed A, B and C"
    - Ontology grounding: only emits if subject OR object is known entity

    Returns list of relationship dicts with provenance.
    """
    known_lower = {e.lower() for e in known_entities if e}
    doc = nlp(text[:nlp.max_length])
    triples = []

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if len(sent_text) < 10:
            continue

        for tok in sent:
            # Only consider real verbs
            if tok.pos_ != "VERB":
                continue
            if tok.tag_ in ("MD",):  # skip modals
                continue

            verb_lemma = tok.lemma_.lower()

            # Skip reporter verbs
            if verb_lemma in REPORTER_VERBS:
                continue

            # Must be a CTI-relevant verb
            if verb_lemma not in CTI_VERBS:
                continue

            # ── PASSIVE VOICE ──
            is_passive = any(c.dep_ == "auxpass" for c in tok.children)

            if is_passive:
                # Passive: "X was VERBed by Y"
                # nsubjpass = the object (what was acted on)
                # agent/pobj = the real subject (who did it)
                passive_obj = None
                agent = None

                for child in tok.children:
                    if child.dep_ == "nsubjpass":
                        passive_obj = child
                    if child.dep_ == "agent":
                        for pobj_child in child.children:
                            if pobj_child.dep_ == "pobj":
                                agent = pobj_child

                if passive_obj and agent:
                    subj_entity = _resolve_subject_entity(agent, known_lower)
                    obj_text = _resolve_full_subject(passive_obj)
                    obj_entity = None
                    for ent in known_lower:
                        if ent in obj_text.lower():
                            obj_entity = ent
                            break

                    # Must have at least one grounded entity
                    if subj_entity or obj_entity:
                        triples.append({
                            "source": subj_entity or _resolve_full_subject(agent),
                            "relationship": verb_lemma,
                            "target": obj_entity or obj_text,
                            "evidence": sent_text,
                            "voice": "passive",
                            "source_grounded": subj_entity is not None,
                            "target_grounded": obj_entity is not None,
                        })

            else:
                # ── ACTIVE VOICE ──
                subject_tok = None
                object_toks = []

                for child in tok.children:
                    if child.dep_ in ("nsubj",):
                        subject_tok = child
                    if child.dep_ in ("dobj", "attr"):
                        object_toks.append(child)
                    # Prepositional objects for verbs like "connect to X"
                    if child.dep_ == "prep":
                        for pobj in child.children:
                            if pobj.dep_ == "pobj":
                                object_toks.append(pobj)
                    # Complement clauses: "leverage X to recover Y"
                    # The dobj of the complement is also relevant
                    if child.dep_ in ("ccomp", "xcomp"):
                        for grandchild in child.children:
                            if grandchild.dep_ in ("nsubj", "dobj"):
                                object_toks.append(grandchild)

                # If no direct subject, check if verb is an acl modifier
                # "The group [deployed X]" — group is ROOT, deployed is acl
                if not subject_tok and tok.dep_ in ("acl", "relcl", "advcl"):
                    head = tok.head
                    if head.pos_ in ("NOUN", "PROPN"):
                        subject_tok = head

                if not subject_tok or not object_toks:
                    continue

                # Resolve subject
                subj_entity = _resolve_subject_entity(subject_tok, known_lower)

                # Resolve each object (with conjunction splitting)
                for obj_tok in object_toks:
                    resolved_objects = _resolve_objects(obj_tok, known_lower)

                    for obj_text, obj_entity in resolved_objects:
                        if not obj_text or len(obj_text) < 2:
                            continue

                        # Must have at least one grounded entity
                        if subj_entity or obj_entity:
                            triples.append({
                                "source": subj_entity or _resolve_full_subject(subject_tok),
                                "relationship": verb_lemma,
                                "target": obj_entity or obj_text,
                                "evidence": sent_text,
                                "voice": "active",
                                "source_grounded": subj_entity is not None,
                                "target_grounded": obj_entity is not None,
                            })

    return triples


# ============================================================
# ONTOLOGY-GROUNDED FILTERING
# ============================================================

def filter_grounded_relationships(
    triples: list[dict],
    require_both: bool = False,
) -> list[dict]:
    """
    Filter relationships to only those grounded in known entities.

    require_both=False: at least one side must be a known entity (default)
    require_both=True: both sides must be known entities (strict)
    """
    kept = []
    for t in triples:
        src_grounded = t.get("source_grounded", False)
        tgt_grounded = t.get("target_grounded", False)

        if require_both and not (src_grounded and tgt_grounded):
            continue
        if not require_both and not (src_grounded or tgt_grounded):
            continue

        # Remove self-references
        if t["source"].lower() == t["target"].lower():
            continue

        kept.append(t)

    return kept


# ============================================================
# DEDUP + CONFIDENCE
# ============================================================

def dedup_triples(triples: list[dict]) -> list[dict]:
    """
    Deduplicate by (source, relationship, target).
    Multiple evidence sentences boost confidence.
    """
    seen = {}
    for t in triples:
        key = (t["source"].lower(), t["relationship"], t["target"].lower())
        if key not in seen:
            seen[key] = {
                "source": t["source"],
                "relationship": t["relationship"],
                "target": t["target"],
                "confidence": 0.70,
                "evidence": [t["evidence"]],
                "source_context": "sentence",
                "source_grounded": t.get("source_grounded", False),
                "target_grounded": t.get("target_grounded", False),
            }
        else:
            if t["evidence"] not in seen[key]["evidence"]:
                seen[key]["evidence"].append(t["evidence"])
                seen[key]["confidence"] = min(seen[key]["confidence"] + 0.08, 0.95)

    return list(seen.values())
