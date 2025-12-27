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


KILL_CHAIN_KEYWORDS = {
    "reconnaissance": ["probe", "scan", "discover", "identify"],
    "discovery": ["enumerate", "list", "inspect"],
    "collection": ["collect", "gather", "read"],
    "exfiltration": ["exfil", "upload", "transfer"],
    "defense-evasion": ["delete", "tamper", "hide"],
    "impact": ["encrypt", "destroy", "wipe"],
}

def _log(msg: str):
    print(f"[MITRE-SEM] {msg}")

def normalize_behavior(text: str):
    t = text.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def embed(text: str):
    """
    Placeholder embedding function.
    Replace with MiniLM or mpnet later.
    """
    vec = np.zeros(300)
    for i, ch in enumerate(text[:300]):
        vec[i] = ord(ch)
    return vec / (np.linalg.norm(vec) + 1e-6)

def cosine(a, b):
    return (a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6)
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

def infer_killchain(text: str) -> str:
    t = text.lower()

    if any(w in t for w in ("phishing", "credential", "social engineering")):
        return "initial-access"

    if any(w in t for w in ("execute", "run", "launch", "payload")):
        return "execution"

    if any(w in t for w in ("persist", "boot", "autorun", "startup")):
        return "persistence"

    if any(w in t for w in ("enumerate", "scan", "discover", "recon")):
        return "discovery"

    if any(w in t for w in ("move laterally", "pivot", "remote", "lateral movement")):
        return "lateral-movement"

    if any(w in t for w in ("collect", "gather", "archive", "prepare")):
        return "collection"

    if any(w in t for w in ("exfil", "upload", "steal", "transfer")):
        return "exfiltration"

    return "unknown"

def clean_ir_nlp_layer2(ir: dict, taxonomy: dict) -> dict:
    """
    Layer-3 transforms behaviors into:
        - normalized form
        - semantic vector hints
        - kill-chain classifications

    It MUST NOT attach technique IDs — MITRE happens afterward.
    """

    new_behaviors = []

    for b in ir.get("behaviors", []):
        if isinstance(b, str):
            text = b.strip()
            desc = text
        elif isinstance(b, dict):
            desc = b.get("description", "").strip()
        else:
            continue

        if not desc:
            continue

        entry = {
            "description": desc,
            "normalized": re.sub(r"\s+", " ", desc.lower()).strip(),
            "semantic_vector": behavior_vector(desc),
            "kill_chain_phase": infer_killchain(desc),
        }

        new_behaviors.append(entry)

    ir["behaviors"] = new_behaviors
    return ir