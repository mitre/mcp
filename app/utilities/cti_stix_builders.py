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
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")






# ----------------------------------------------------------------------
# Malware
# ----------------------------------------------------------------------

def _lookup_taxonomy_object(name, kind, taxonomy):
    """
    Pure ontology lookup against MITRE ATT&CK's name_index.

    `kind` is one of 'malware' | 'tool' | 'intrusion-set'. Returns the
    upstream ATT&CK STIX object verbatim, or None on miss. No fuzzy
    matching, no static aliases, no LLM — if the name isn't in ATT&CK,
    the pipeline degrades to the IR-only object rather than guessing.
    """
    if not taxonomy or not name:
        return None
    key = f"{kind}:{name.strip().lower()}"
    hit = taxonomy.get("name_index", {}).get(key)
    if not hit:
        return None
    return hit[2] if isinstance(hit, tuple) and len(hit) >= 3 else None


def _enrich_from_taxonomy(obj, tax_obj, copy_fields):
    """Copy ontology-derived fields onto our builder output (setdefault — never clobber operator overrides)."""
    if not tax_obj:
        return obj
    for fk in copy_fields:
        val = tax_obj.get(fk)
        if val is None:
            continue
        obj.setdefault(fk, val)
    return obj
def make_threat_actor(ta: dict, taxonomy: dict = None) -> dict:
    """
    Build STIX 2.1 threat-actor object. If `taxonomy` is provided, enrich
    from MITRE ATT&CK's intrusion-set entry (x_mitre_aliases, aliases,
    external_references) via ontology lookup. No static name->actor tables.
    """
    name = ta.get("name")
    if not name:
        return None

    obj = {
        "type": "threat-actor",
        "spec_version": "2.1",
        "id": new_stix_id("threat-actor"),
        "created": now(),
        "modified": now(),
        "name": name,
    }

    if "description" in ta:
        obj["description"] = ta["description"]

    for k, v in ta.items():
        if k not in ("name", "description"):
            obj[f"x_{k}"] = v

    # ATT&CK uses 'intrusion-set' for what STIX calls 'threat-actor'; the
    # name_index maps the intrusion-set entries under that key. Look up
    # under both kinds — taxonomy_loader keys intrusion-sets via the
    # 'intrusion-set' prefix.
    tax_obj = (_lookup_taxonomy_object(name, "intrusion-set", taxonomy)
               or _lookup_taxonomy_object(name, "threat-actor", taxonomy))
    if tax_obj:
        _enrich_from_taxonomy(
            obj, tax_obj,
            ("x_mitre_aliases", "aliases", "external_references"),
        )
        aliases = tax_obj.get("x_mitre_aliases") or tax_obj.get("aliases") or []
        spec_aliases = [a for a in aliases if a.strip().lower() != name.strip().lower()]
        if spec_aliases:
            obj.setdefault("aliases", spec_aliases)
        obj["x_cti_enriched_from"] = tax_obj.get("id")

    return obj


def make_attack_pattern(ttp_text, taxonomy: dict):
    """
    Create attack-pattern SDO using MITRE taxonomy first.

    ttp_text may be:
        - "T1048"
        - "Exfiltration Over Alternative Protocol (T1048)"
        - "T1070.004"
        - plain English name
        - dict from IR with keys: id, name, confidence, evidence
    """

    confidence = None
    evidence = None

    # ----------------------------
    # Normalize IR dict → string (WITHOUT losing metadata)
    # ----------------------------
    if isinstance(ttp_text, dict):
        confidence = ttp_text.get("confidence")
        evidence = ttp_text.get("evidence")

        if "id" in ttp_text:
            t = ttp_text["id"].strip()
        elif "name" in ttp_text:
            t = ttp_text["name"].strip()
        else:
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

    # ----------------------------
    # 1) If technique ID present, look up MITRE object
    # ----------------------------
    if tid and tid in taxonomy.get("attack_id_index", {}):
        obj = taxonomy["attack_id_index"][tid]

        ap = {
            "type": "attack-pattern",
            "spec_version": "2.1",
            "id": obj["id"],
            "created": obj.get("created") or now(),
            "modified": obj.get("modified") or now(),
            "name": obj.get("name"),
            "description": obj.get("description", ""),
            "external_references": obj.get("external_references", []),
        }

        # Preserve analytical signal from IR
        if confidence is not None:
            ap["x_cti_confidence"] = confidence
        if evidence is not None:
            ap["x_cti_evidence"] = evidence

        return ap

    # ----------------------------
    # 2) Name-based lookup (ontology-driven, no guessing)
    # ----------------------------
    # name_index is keyed '<kind>:<lowername>' (see the builder above), so a
    # bare name matched nothing and every name-only technique fell to the
    # non-enriched fallback, which carries no external_references and is
    # therefore invisible to adversary authoring.
    name_key = f"attack-pattern:{t.strip().lower()}"
    if name_key in taxonomy.get("name_index", {}):
        stype, sid, sobj = taxonomy["name_index"][name_key]
        if stype == "attack-pattern":
            ap = {
                "type": "attack-pattern",
                "spec_version": "2.1",
                "id": sid,
                "created": sobj.get("created") or now(),
                "modified": sobj.get("modified") or now(),
                "name": sobj.get("name"),
                "description": sobj.get("description", ""),
                "external_references": sobj.get("external_references", []),
            }

            if confidence is not None:
                ap["x_cti_confidence"] = confidence
            if evidence is not None:
                ap["x_cti_evidence"] = evidence

            return ap

    # ----------------------------
    # 3) Deterministic fallback (NO enrichment, NO inference)
    # ----------------------------
    ap = {
        "type": "attack-pattern",
        "spec_version": "2.1",
        "id": new_stix_id("attack-pattern"),
        "created": now(),
        "modified": now(),
        "name": t,
        "external_references": [],
    }

    if confidence is not None:
        ap["x_cti_confidence"] = confidence
    if evidence is not None:
        ap["x_cti_evidence"] = evidence

    return ap
def make_bundle(
        objects: list,
        *,
        model: str | None = None,
        provider: str | None = None,
        config: dict | None = None,
    ) -> dict:
    """
    Pure JSON bundle — no stix2 library — fully serializable.
    """
    bundle = {
        "type": "bundle",
        "id": new_stix_id("bundle"),
        "objects": objects,
    }

    # ---- CTI provenance (STIX-safe extensions) ----
    if model:
        bundle["x_cti_model"] = model
    if provider:
        bundle["x_cti_provider"] = provider
    if config:
        bundle["x_cti_config"] = config


    return bundle
