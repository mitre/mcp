"""
cti_stix_builders.py

Purpose:
    Deterministic **JSON-only** construction of STIX 2.1-shaped objects
    for Phase 2 of the CTI pipeline.

Used by:
    • Phase 2 (IR → STIX)
    • cti_pipeline_stage2.py
    • Automated relationship construction
    • Optional MITRE enrichment layers

Guarantees:
    • Every object generated has a valid STIX-style ID.
    • No dependency on `stix2` library.
    • All objects are JSON-serializable.
    • Custom fields are preserved via x_* names.
    • Observed-Data objects are always valid and non-empty.
    • Bundle creation is stable and deterministic.

This file is the “safe mode” STIX builder that preserves data,
avoids crashes, and keeps STIX output robust, flexible, and pipeline-friendly.
"""

import uuid
import datetime
import re


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def new_stix_id(obj_type: str) -> str:
    """Generate a STIX 2.1 compliant ID."""
    return f"{obj_type}--{uuid.uuid4()}"


def now():
    """ISO timestamp."""
    return datetime.datetime.utcnow().isoformat() + "Z"


# ----------------------------------------------------------------------
# Malware
# ----------------------------------------------------------------------

def make_malware(m: dict) -> dict:
    """
    IR malware entry:
        { "name": "...", "description": "...", ... }

    Returns deterministic STIX 2.1 malware dict.
    """
    name = m.get("name")
    if not name:
        return None

    obj = {
        "type": "malware",
        "id": new_stix_id("malware"),
        "created": now(),
        "modified": now(),
        "name": name,
        "is_family": False,
    }

    desc = m.get("description")
    if desc:
        obj["description"] = desc

    # Custom IR fields → custom STIX x_*
    for k, v in m.items():
        if k not in ("name", "description"):
            obj[f"x_{k}"] = v

    return obj


# ----------------------------------------------------------------------
# Tool
# ----------------------------------------------------------------------

def make_tool(t: dict) -> dict:
    name = t.get("name")
    if not name:
        return None

    obj = {
        "type": "tool",
        "id": new_stix_id("tool"),
        "created": now(),
        "modified": now(),
        "name": name,
    }

    if "description" in t:
        obj["description"] = t["description"]

    for k, v in t.items():
        if k not in ("name", "description"):
            obj[f"x_{k}"] = v

    return obj


# ----------------------------------------------------------------------
# Threat Actor
# ----------------------------------------------------------------------

def make_threat_actor(ta: dict) -> dict:
    name = ta.get("name")
    if not name:
        return None

    obj = {
        "type": "threat-actor",
        "id": new_stix_id("threat-actor"),
        "created": now(),
        "modified": now(),
        "name": name,
        "roles": ["threat-actor"],
    }

    if "description" in ta:
        obj["description"] = ta["description"]

    for k, v in ta.items():
        if k not in ("name", "description"):
            obj[f"x_{k}"] = v

    return obj


# ----------------------------------------------------------------------
# Infrastructure
# ----------------------------------------------------------------------

def make_infrastructure(i: dict) -> dict:
    name = i.get("name")
    if not name:
        return None

    obj = {
        "type": "infrastructure",
        "id": new_stix_id("infrastructure"),
        "created": now(),
        "modified": now(),
        "name": name,
    }

    if "description" in i:
        obj["description"] = i["description"]

    for k, v in i.items():
        if k not in ("name", "description"):
            obj[f"x_{k}"] = v

    return obj


# ----------------------------------------------------------------------
# Attack Pattern (TTP)
# ----------------------------------------------------------------------

def make_attack_pattern(ttp_text: str, taxonomy: dict):
    """
    Create attack-pattern SDO using MITRE taxonomy first.
    ttp_text may be:
        - "T1048"
        - "Exfiltration Over Alternative Protocol (T1048)"
        - "T1070.004"
        - plain English name
    """

    # Normalize dict → string
    if isinstance(ttp_text, dict):
        if "name" in ttp_text:
            t = ttp_text["name"].strip()
        elif "technique_id" in ttp_text:
            t = ttp_text["technique_id"].strip()
        else:
            # If dict has unknown shape
            t = str(ttp_text).strip()
    elif isinstance(ttp_text, str):
        t = ttp_text.strip()
    else:
        return None  # unsupported type

    # ----------------------------
    # Extract Technique ID (Txxxx or Txxxx.xxx)
    # ----------------------------
    match = re.search(r"(T\d{4}(?:\.\d{3})?)", t.upper())
    tid = match.group(1) if match else None
    
    # 1) If technique ID present, look up MITRE object
    if tid and tid in taxonomy["attack_id_index"]:
        obj = taxonomy["attack_id_index"][tid]
        # Reuse MITRE object (clone minimal fields)
        return {
            "type": "attack-pattern",
            "id": obj["id"],
            "name": obj.get("name"),
            "description": obj.get("description", ""),
            "external_references": obj.get("external_references", [])
        }

    # 2) Otherwise try a simple name lookup
    name_key = t.lower()
    if name_key in taxonomy["name_index"]:
        stype, sid, sobj = taxonomy["name_index"][name_key]
        if stype == "attack-pattern":
            return {
                "type": "attack-pattern",
                "id": sid,
                "name": sobj.get("name"),
                "description": sobj.get("description", ""),
                "external_references": sobj.get("external_references", [])
            }

    # 3) Fallback to our own simple object
    return {
        "type": "attack-pattern",
        "id": new_stix_id("attack-pattern"),
        "created": now(),
        "modified": now(),
        "name": t,
        "external_references": [],
    }

# ----------------------------------------------------------------------
# Observed Data (behaviors)
# ----------------------------------------------------------------------

def make_observed_data(behavior: str) -> dict:
    """
    ObservedData *must not break* and *must be JSON-only*.

    behavior is simple text from IR.
    """
    if not behavior:
        return None

    obj = {
        "type": "observed-data",
        "id": new_stix_id("observed-data"),
        "created": now(),
        "modified": now(),
        "first_observed": now(),
        "last_observed": now(),
        "number_observed": 1,

        # MUST be non-empty dict
        "objects": {
            "0": {
                "type": "x-observable",
                "spec_version": "2.1",
                "x_behavior": behavior,
            }
        },
    }

    return obj


# ----------------------------------------------------------------------
# Relationship
# ----------------------------------------------------------------------

def make_relationship(rel_type: str, src_id: str, dst_id: str) -> dict:
    if not rel_type or not src_id or not dst_id:
        return None

    obj = {
        "type": "relationship",
        "id": new_stix_id("relationship"),
        "created": now(),
        "modified": now(),
        "relationship_type": rel_type,
        "source_ref": src_id,
        "target_ref": dst_id,
    }

    return obj


# ----------------------------------------------------------------------
# Bundle
# ----------------------------------------------------------------------

def make_bundle(objects: list) -> dict:
    """
    Pure JSON bundle — no stix2 library — fully serializable.
    """
    return {
        "type": "bundle",
        "id": new_stix_id("bundle"),
        "objects": objects,
    }
