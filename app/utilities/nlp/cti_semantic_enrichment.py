"""
NLP Layer 3 — Semantic Enrichment

This module provides:
    - lightweight embeddings for behaviors
    - cosine similarity scoring vs MITRE technique descriptions
    - kill-chain inference based on linguistic cues
    - enriched IR["technique_mappings"]
"""

import numpy as np
import re
import math
import hashlib


def _log(msg: str):
    print(f"[MITRE-SEM] {msg}")
# ---------------------------------------------------------------------------
# MAIN LAYER 3 PIPELINE
# ---------------------------------------------------------------------------

def behavior_vector(text: str) -> list[float]:
    """
    Deterministic pseudo-semantic vector generator.
    (We do NOT call embeddings here to avoid nondeterministic behavior.)
    """
    h = hashlib.sha256(text.lower().encode()).digest()
    # produce 8 stable floats between -1 and +1
    return [((b / 255.0) * 2 - 1) for b in h[:8]]

def clean_ir_nlp_layer2(ir: dict, taxonomy: dict) -> dict:
    """
    Layer-2 semantic enrichment.

    Adds:
      - normalized behavior text
      - deterministic semantic vectors

    Does NOT:
      - replace behaviors
      - infer kill-chain
      - attach MITRE techniques
      - modify relationships
    """

    for b in ir.get("behaviors", []):
        if not isinstance(b, dict):
            continue

        desc = b.get("description")
        if not desc:
            continue

        b.setdefault(
            "normalized",
            re.sub(r"\s+", " ", desc.lower()).strip()
        )
        b.setdefault(
            "semantic_vector",
            behavior_vector(desc)
        )

    existing_relationships = ir.get("relationships", [])

    if existing_relationships:
        ir["relationships"] = existing_relationships

    return ir
