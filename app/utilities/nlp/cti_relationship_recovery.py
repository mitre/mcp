"""
NLP Layer 2 — Relationship Recovery

This module reconstructs missing relationships by:
    - Extracting SVO structures from dependency parses
    - Fuzzy-matching subjects/objects to known entity names
    - Merging + deduping recovered relationships
"""

import spacy
import re
from rapidfuzz import fuzz

nlp = spacy.load("en_core_web_sm")

def _log(msg: str):
    print(f"[RELREC] {msg}")

def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())

# ---------------------------------------------------------------------------
# Recover SVO relationships
# ---------------------------------------------------------------------------

def recover_relationships_from_dependencies(ir, doc):
    """
    Returns a list of recovered relationships:
        { "source": "...", "relationship": "...", "target": "...", "sentence": "..." }
    """
    relationships = []

    # build map: canonical → original name
    existing = {}
    for section in ("malware", "tools", "infrastructure", "threat_actors"):
        for e in ir.get(section, []):
            can = norm(e.get("name", ""))
            existing[can] = e.get("name")

    for sent in doc.sents:
        root = sent.root
        if root.pos_ != "VERB":
            continue

        subj = None
        obj = None

        for child in root.children:
            if child.dep_ == "nsubj":
                subj = child
            if child.dep_ in ("dobj", "pobj", "attr", "dative"):
                obj = child

        if not subj or not obj:
            continue

        subj_key = norm(subj.text)
        obj_key = norm(obj.text)

        # fuzzy match both sides
        best_subj = None
        best_obj = None

        for k, v in existing.items():
            if fuzz.ratio(subj_key, k) > 90:
                best_subj = v
            if fuzz.ratio(obj_key, k) > 90:
                best_obj = v

        if best_subj and best_obj:
            relationships.append({
                "source": best_subj,
                "relationship": root.lemma_,
                "target": best_obj,
                "sentence": sent.text.strip(),
                "source_layer": "nlp-layer2"
            })

    _log(f"Recovered {len(relationships)} relationships from dependencies")
    return relationships

# ---------------------------------------------------------------------------
# MAIN LAYER 2 PIPELINE
# ---------------------------------------------------------------------------

def clean_ir_nlp_layer2(ir: dict, original_text: str) -> dict:
    """
    Enhance IR relationships by inserting dependency-based SVO results.
    """
    _log("Beginning NLP Layer #2")
    doc = nlp(original_text)

    recovered = recover_relationships_from_dependencies(ir, doc)

    # merge with existing relationships
    merged = ir.get("relationships", []) + recovered

    # dedupe by (src, rel, tgt)
    unique = {}
    for r in merged:
        key = (
            r.get("source", "").lower(),
            r.get("relationship", ""),
            r.get("target", "").lower()
        )
        unique[key] = r

    ir["relationships"] = list(unique.values())
    _log(f"Relationships after Layer 2: {len(ir['relationships'])}")
    _log("Completed NLP Layer #2")

    return ir
