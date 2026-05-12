"""Deterministic multi-source STIX bundle fusion for the CTI pipeline."""

from __future__ import annotations

import datetime
import json
import re
import uuid


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _norm(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")


def _external_id(obj: dict, source_name: str) -> str | None:
    wanted = source_name.lower()
    for er in obj.get("external_references") or []:
        if (er.get("source_name") or "").lower() == wanted:
            val = (er.get("external_id") or "").strip()
            if val:
                return val
    return None


def _cve_id(obj: dict) -> str | None:
    direct = _external_id(obj, "cve")
    if direct:
        return direct.upper()
    for field in ("name", "description"):
        val = obj.get(field)
        if not isinstance(val, str):
            continue
        m = re.search(r"CVE-\d{4}-\d{4,7}", val, flags=re.I)
        if m:
            return m.group(0).upper()
    return None


def canonical_object_key(obj: dict) -> str:
    otype = obj.get("type") or "object"
    if otype == "attack-pattern":
        tid = _external_id(obj, "mitre-attack")
        if tid:
            return f"attack-pattern:{tid.upper()}"
    if otype == "vulnerability":
        cve = _cve_id(obj)
        if cve:
            return f"vulnerability:{cve}"
    if otype == "software":
        cpe = obj.get("cpe")
        if cpe:
            return f"software:cpe:{cpe}"
        return "software:{}:{}:{}".format(
            _norm(obj.get("vendor") or ""),
            _norm(obj.get("name") or ""),
            _norm(obj.get("version") or ""),
        )
    if otype == "relationship":
        return f"relationship:{obj.get('id')}"
    name = obj.get("name")
    if name and otype in {
        "campaign", "identity", "infrastructure", "intrusion-set",
        "malware", "threat-actor", "tool",
    }:
        return f"{otype}:{_norm(name)}"
    return f"{otype}:{obj.get('id') or json.dumps(obj, sort_keys=True, default=str)}"


def _merge_values(old, new):
    if old in (None, "", [], {}):
        return new
    if new in (None, "", [], {}):
        return old
    if isinstance(old, list) and isinstance(new, list):
        out = list(old)
        seen = {json.dumps(v, sort_keys=True, default=str) for v in out}
        for item in new:
            key = json.dumps(item, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out
    if isinstance(old, dict) and isinstance(new, dict):
        out = dict(old)
        for k, v in new.items():
            out[k] = _merge_values(out.get(k), v)
        return out
    return old


def _merge_objects(existing: dict, incoming: dict) -> dict:
    out = dict(existing)
    for k, v in incoming.items():
        if k == "id":
            continue
        out[k] = _merge_values(out.get(k), v)
    fused = list(out.get("x_cti_fused_from") or [])
    for oid in (existing.get("id"), incoming.get("id")):
        if oid and oid not in fused:
            fused.append(oid)
    if fused:
        out["x_cti_fused_from"] = fused
    return out


def fuse_bundles(bundles: list[dict]) -> dict:
    """
    Merge STIX bundles by stable canonical keys, remapping relationships to
    the surviving object IDs.
    """
    objects_by_key: dict[str, dict] = {}
    id_to_key: dict[str, str] = {}
    relationship_inputs: list[dict] = []

    for bundle in bundles or []:
        for obj in bundle.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            if obj.get("type") == "relationship":
                relationship_inputs.append(dict(obj))
                continue
            key = canonical_object_key(obj)
            if key in objects_by_key:
                objects_by_key[key] = _merge_objects(objects_by_key[key], obj)
            else:
                objects_by_key[key] = dict(obj)
            if obj.get("id"):
                id_to_key[obj["id"]] = key

    relationships_by_key: dict[tuple[str, str, str], dict] = {}
    for rel in relationship_inputs:
        src_key = id_to_key.get(rel.get("source_ref"))
        tgt_key = id_to_key.get(rel.get("target_ref"))
        if not (src_key and tgt_key):
            continue
        src_id = objects_by_key[src_key].get("id")
        tgt_id = objects_by_key[tgt_key].get("id")
        rel["source_ref"] = src_id
        rel["target_ref"] = tgt_id
        rkey = (src_id, rel.get("relationship_type") or "related-to", tgt_id)
        if rkey in relationships_by_key:
            relationships_by_key[rkey] = _merge_objects(relationships_by_key[rkey], rel)
        else:
            relationships_by_key[rkey] = rel

    fused_objects = list(objects_by_key.values()) + list(relationships_by_key.values())
    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "objects": fused_objects,
        "x_cti_fusion": {
            "source_bundle_count": len(bundles or []),
            "object_count": len(fused_objects),
            "created": _now(),
        },
    }
