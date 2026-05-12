"""
STIX 2.1 Validation (Lightweight)
--------------------------------
This validator focuses on basic structural correctness of bundles produced
by Phase 2. It is intentionally lightweight and does NOT enforce the full
OASIS STIX specification.

Checks include:
- bundle/type/id correctness
- object IDs valid and unique
- required fields per object type
- relationship integrity (source_ref, target_ref)
- unknown object types
"""

import uuid


# -----------------------------
# Basic allowed STIX object types
# -----------------------------
ALLOWED_STIX_TYPES = {
    "attack-pattern",
    "campaign",
    "course-of-action",
    "identity",
    "indicator",
    "intrusion-set",
    "infrastructure",
    "location",
    "malware",
    "note",
    "observed-data",
    "report",
    "threat-actor",
    "tool",
    "user-account",
    "vulnerability",
    "relationship",
}


# -----------------------------
# Validation Helper Functions
# -----------------------------

def valid_uuid4(s: str) -> bool:
    try:
        uuid_obj = uuid.UUID(s, version=4)
        return True
    except Exception:
        return False


def valid_stix_id(stix_type: str, stix_id: str) -> bool:
    """
    Check if ID matches "<type>--<uuid4>".
    """
    if not isinstance(stix_id, str) or "--" not in stix_id:
        return False

    prefix, rest = stix_id.split("--", 1)
    if prefix != stix_type:
        return False

    return valid_uuid4(rest)


# -----------------------------
# Main Validation
# -----------------------------

def validate_bundle(bundle: dict) -> list:
    """
    Validate a STIX bundle at a structural level.

    Returns:
        list of error messages (empty → fully valid)
    """
    errors = []

    # --- Bundle type and structure ---
    if bundle.get("type") != "bundle":
        errors.append('Bundle "type" must be "bundle".')

    if "id" not in bundle:
        errors.append('Bundle missing required field "id".')
    else:
        if not valid_stix_id("bundle", bundle["id"]):
            errors.append(f'Bundle id "{bundle["id"]}" is not a valid bundle--<uuid4>.')

    objs = bundle.get("objects", [])
    if not isinstance(objs, list):
        errors.append('"objects" must be a list.')
        return errors

    if len(objs) == 0:
        errors.append("Bundle contains zero STIX objects.")
        return errors

    # Collect IDs for relationship checks
    id_map = {}
    for i, obj in enumerate(objs):
        # Must be dict
        if not isinstance(obj, dict):
            errors.append(f"Object {i} is not a JSON object.")
            continue

        # Must have type
        t = obj.get("type")
        if not t:
            errors.append(f"Object {i} missing 'type'.")
            continue

        # Must have id
        oid = obj.get("id")
        if not oid:
            errors.append(f"Object {i} of type '{t}' missing 'id'.")
            continue

        # Validate object ID shape
        if not valid_stix_id(t, oid):
            errors.append(f"Object {i} ID '{oid}' does not match {t}--<uuid4>.")

        # Detect duplicates
        if oid in id_map:
            errors.append(f"Duplicate STIX ID detected: {oid}")
        else:
            id_map[oid] = t

        # Validate object type against allowed types
        if t not in ALLOWED_STIX_TYPES:
            errors.append(f"Unknown STIX type '{t}' in object {i}.")

    # --- Relationship validation ---
    for i, obj in enumerate(objs):
        if obj.get("type") != "relationship":
            continue

        rel = obj.get("relationship_type")
        src = obj.get("source_ref")
        tgt = obj.get("target_ref")

        if not rel:
            errors.append(f"Relationship {i} missing 'relationship_type'.")
        if not src:
            errors.append(f"Relationship {i} missing 'source_ref'.")
        if not tgt:
            errors.append(f"Relationship {i} missing 'target_ref'.")

        # Referential integrity
        if src and src not in id_map:
            errors.append(f"Relationship {i} source_ref '{src}' does not exist.")
        if tgt and tgt not in id_map:
            errors.append(f"Relationship {i} target_ref '{tgt}' does not exist.")

    return errors
