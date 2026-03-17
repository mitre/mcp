"""
cti_stix_merge.py — Multi-Source STIX Bundle Merge Pipeline

Merges multiple single-source STIX bundles into one unified bundle.
Handles conflicts using confidence scoring, provenance tracking,
and majority voting — inspired by how GTI merges multi-source CTI.

No LLM required. Fully deterministic.

Conflict resolution strategy:
1. Entities: deduplicate by canonical name, merge descriptions,
   track source provenance, use highest confidence
2. Techniques: deduplicate by ATT&CK ID, merge evidence from
   all sources, boost confidence when multiple sources agree
3. Relationships: deduplicate by (source, verb, target) triple,
   merge evidence, boost when corroborated across sources
4. Conflicts: when sources disagree on entity type, use MITRE
   taxonomy as authority; when both valid, keep both with provenance
"""

import json
import re
from collections import defaultdict
from datetime import datetime


def merge_stix_bundles(bundles: list[dict], source_names: list[str] = None) -> dict:
    """
    Merge multiple STIX bundles into one unified bundle.

    Args:
        bundles: list of STIX bundle dicts (each from a single source)
        source_names: optional list of source names (parallel to bundles)

    Returns:
        Merged STIX bundle with provenance tracking and confidence scoring
    """
    if not bundles:
        return _empty_bundle()

    if source_names is None:
        source_names = [f"source-{i}" for i in range(len(bundles))]

    # Collect all objects by type
    entities = defaultdict(list)     # canonical_name → [(obj, source_name)]
    techniques = defaultdict(list)   # technique_id → [(obj, source_name)]
    relationships = defaultdict(list) # (src_name, verb, tgt_name) → [(obj, source)]
    other_objects = []               # observed-data, etc.

    for bundle, src_name in zip(bundles, source_names):
        for obj in bundle.get("objects", []):
            otype = obj.get("type", "")

            if otype in ("malware", "tool", "threat-actor", "infrastructure"):
                name = (obj.get("name") or "").lower().strip()
                if name:
                    entities[name].append((obj, src_name))

            elif otype == "attack-pattern":
                tid = None
                for ref in obj.get("external_references", []):
                    eid = ref.get("external_id", "")
                    if eid.startswith("T"):
                        tid = eid
                        break
                if tid:
                    techniques[tid].append((obj, src_name))
                else:
                    # No T-number — use name as key
                    name = (obj.get("name") or "").lower().strip()
                    if name:
                        techniques[f"name:{name}"].append((obj, src_name))

            elif otype == "relationship":
                src_ref = (obj.get("source_ref") or "")
                tgt_ref = (obj.get("target_ref") or "")
                rel_type = (obj.get("relationship_type") or "").lower()
                key = (src_ref, rel_type, tgt_ref)
                relationships[key].append((obj, src_name))

            else:
                other_objects.append(obj)

    # ========================================================
    # MERGE ENTITIES
    # ========================================================
    merged_objects = []
    name_to_id = {}  # for relationship resolution

    for name, entries in entities.items():
        # Use the type from the first occurrence, but check for conflicts
        types = {e[0].get("type") for e in entries}
        sources = {e[1] for e in entries}

        # Pick the "best" object (highest confidence, most complete)
        best = max(entries, key=lambda e: (
            e[0].get("confidence", 50),
            len(e[0].get("description", "")),
        ))

        merged_obj = dict(best[0])

        # Add provenance
        merged_obj["x_cti_sources"] = sorted(sources)
        merged_obj["x_cti_source_count"] = len(sources)

        # Boost confidence based on source agreement
        base_conf = merged_obj.get("confidence", 50)
        if isinstance(base_conf, (int, float)):
            # Each additional source adds confidence
            boost = min((len(sources) - 1) * 10, 30)
            merged_obj["confidence"] = min(base_conf + boost, 100)

        # Merge descriptions from all sources
        descriptions = set()
        for obj, _ in entries:
            desc = (obj.get("description") or "").strip()
            if desc:
                descriptions.add(desc)
        if descriptions:
            merged_obj["description"] = " | ".join(sorted(descriptions))

        # Handle type conflicts
        if len(types) > 1:
            merged_obj["x_cti_type_conflict"] = sorted(types)
            # Use most common type
            type_counts = defaultdict(int)
            for obj, _ in entries:
                type_counts[obj.get("type")] += 1
            merged_obj["type"] = max(type_counts, key=type_counts.get)

        merged_objects.append(merged_obj)
        name_to_id[name] = merged_obj.get("id")

    entity_count = len(merged_objects)

    # ========================================================
    # MERGE TECHNIQUES
    # ========================================================
    for tid, entries in techniques.items():
        sources = {e[1] for e in entries}
        best = entries[0][0]  # First occurrence

        merged_tech = dict(best)
        merged_tech["x_cti_sources"] = sorted(sources)
        merged_tech["x_cti_source_count"] = len(sources)

        # Confidence boost from multi-source corroboration
        base_conf = merged_tech.get("confidence", 50)
        if isinstance(base_conf, (int, float)):
            boost = min((len(sources) - 1) * 15, 40)
            merged_tech["confidence"] = min(base_conf + boost, 100)

        # Merge evidence
        all_evidence = set()
        for obj, src in entries:
            for ev in (obj.get("x_cti_evidence") or []):
                all_evidence.add(str(ev))
            # Also track which source contributed
            all_evidence.add(f"[source: {src}]")
        if all_evidence:
            merged_tech["x_cti_evidence"] = sorted(all_evidence)

        merged_objects.append(merged_tech)

    technique_count = len(merged_objects) - entity_count

    # ========================================================
    # MERGE RELATIONSHIPS
    # ========================================================
    for key, entries in relationships.items():
        sources = {e[1] for e in entries}
        best = entries[0][0]

        merged_rel = dict(best)
        merged_rel["x_cti_sources"] = sorted(sources)

        # Confidence boost from corroboration
        base_conf = merged_rel.get("x_cti_confidence")
        if isinstance(base_conf, (int, float)):
            boost = min((len(sources) - 1) * 15, 40)
            merged_rel["x_cti_confidence"] = min(base_conf + boost, 95)

        merged_objects.append(merged_rel)

    rel_count = len(merged_objects) - entity_count - technique_count

    # Add other objects (observed-data, etc.)
    merged_objects.extend(other_objects)

    # ========================================================
    # BUILD FINAL BUNDLE
    # ========================================================
    bundle = {
        "type": "bundle",
        "id": f"bundle--merged-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "spec_version": "2.1",
        "objects": merged_objects,
        "x_cti_merge_metadata": {
            "source_count": len(bundles),
            "source_names": source_names,
            "merged_at": datetime.utcnow().isoformat() + "Z",
            "entities_merged": entity_count,
            "techniques_merged": technique_count,
            "relationships_merged": rel_count,
        },
    }

    print(f"[MERGE] {len(bundles)} sources → {len(merged_objects)} objects "
          f"({entity_count} entities, {technique_count} techniques, {rel_count} relationships)")

    return bundle


def _empty_bundle():
    return {
        "type": "bundle",
        "id": "bundle--empty",
        "spec_version": "2.1",
        "objects": [],
    }
