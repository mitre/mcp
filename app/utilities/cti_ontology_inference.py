"""
cti_ontology_inference.py — Ontology-Driven Technique Inference

Infers ATT&CK techniques from known tools/malware using the MITRE
taxonomy relationship graph. Zero LLM. Zero network. Pure ontology.

This implements the "senior analyst shortcut":
    "I see Mimikatz → therefore T1003.001 (LSASS Memory)"

Data source: enterprise_attack.json (50MB, already local)
Contains: 20,048 relationships mapping tools/malware → techniques
"""

import re
from functools import lru_cache
from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy


@lru_cache(maxsize=1)
def _build_entity_technique_map():
    """
    Build a mapping: normalized entity name → list of ATT&CK technique IDs.

    Uses MITRE relationships where:
        source = tool/malware (STIX ID)
        relationship_type = "uses"
        target = attack-pattern (STIX ID)
    """
    tax = load_mitre_taxonomy()
    rels = tax["relationships"]
    tools_by_id = tax["tools"]
    malware_by_id = tax["malware"]
    ap_by_id = tax["attack_patterns"]
    attack_id_idx = tax["attack_id_index"]

    # Step 1: Map entity names (including aliases) → STIX ID
    name_to_stix_id = {}
    for obj_id, obj in tools_by_id.items():
        n = obj.get("name", "").lower().strip()
        if n:
            name_to_stix_id[n] = obj_id
        for alias in obj.get("x_mitre_aliases", []):
            name_to_stix_id[alias.lower().strip()] = obj_id

    for obj_id, obj in malware_by_id.items():
        n = obj.get("name", "").lower().strip()
        if n:
            name_to_stix_id[n] = obj_id
        for alias in obj.get("x_mitre_aliases", []):
            name_to_stix_id[alias.lower().strip()] = obj_id

    # Step 2: Map STIX ID → technique IDs via "uses" relationships
    stix_id_to_techniques = {}
    for r in rels:
        if r.get("relationship_type") != "uses":
            continue
        src = r.get("source_ref", "")
        tgt = r.get("target_ref", "")
        if not tgt.startswith("attack-pattern"):
            continue

        ap = ap_by_id.get(tgt)
        if not ap:
            continue

        tid = None
        for ref in ap.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                tid = ref.get("external_id")
                break
        if not tid:
            continue

        stix_id_to_techniques.setdefault(src, []).append(tid)

    # Step 3: Combine into name → technique IDs
    entity_to_techniques = {}
    for name, stix_id in name_to_stix_id.items():
        techs = stix_id_to_techniques.get(stix_id, [])
        if techs:
            entity_to_techniques[name] = techs

    return entity_to_techniques, name_to_stix_id


def infer_techniques_from_entities(
    ir: dict, lookup: dict, source_text: str = ""
) -> list[dict]:
    """
    Given an IR with tools/malware, infer ATT&CK techniques from the
    MITRE taxonomy relationship graph.

    When source_text is provided, techniques are filtered to those
    corroborated by the source text (keyword overlap with technique
    name or description). This prevents tools with broad technique
    profiles (e.g., Cobalt Strike → 72 techniques) from flooding
    the output with irrelevant matches.

    Returns technique objects compatible with the pipeline's attack_patterns format.
    Only returns techniques that exist in the current taxonomy (lookup dict).
    """
    entity_map, _ = _build_entity_technique_map()

    # Collect all entity names from IR
    entity_names = set()
    for group in ("tools", "malware"):
        for ent in ir.get(group, []):
            name = (ent.get("name") or "").strip().lower()
            if name:
                entity_names.add(name)

    # Build source text token set for corroboration
    source_tokens = set()
    if source_text:
        source_tokens = set(re.findall(r"[a-z]{3,}", source_text.lower()))

    # Infer techniques
    inferred = {}
    skipped_no_corroboration = 0

    for name in entity_names:
        techniques = entity_map.get(name, [])
        if not techniques:
            norm = re.sub(r"[^a-z0-9 ]", "", name).strip()
            techniques = entity_map.get(norm, [])

        # Tools with broad profiles (>8 techniques) require text corroboration
        needs_corroboration = len(techniques) > 8 and bool(source_tokens)

        for tid in techniques:
            if tid not in lookup:
                continue

            tech = lookup[tid]

            if needs_corroboration:
                # Check if technique name or description keywords overlap
                # with the source text
                tech_name = (tech.get("name", "") or "").lower()
                tech_desc = (tech.get("description", "") or "").lower()
                tech_tokens = set(re.findall(r"[a-z]{4,}", tech_name))
                tech_tokens |= set(re.findall(r"[a-z]{5,}", tech_desc))
                # Remove very common words
                tech_tokens -= {
                    "attack", "which", "these", "those", "their",
                    "other", "about", "after", "before", "being",
                    "could", "would", "should", "through", "using",
                    "example", "information", "techniques", "adversaries",
                    "system", "systems", "command", "commands",
                }

                overlap = tech_tokens & source_tokens
                if len(overlap) < 3:
                    skipped_no_corroboration += 1
                    continue

            if tid not in inferred:
                inferred[tid] = {
                    "id": tid,
                    "name": tech.get("name", ""),
                    "confidence": 0.90,
                    "evidence": [f"MITRE taxonomy: {name} uses {tid}"],
                    "source": "ontology-inference",
                }
            else:
                inferred[tid]["evidence"].append(
                    f"MITRE taxonomy: {name} uses {tid}")
                inferred[tid]["confidence"] = min(
                    inferred[tid]["confidence"] + 0.03, 0.97)

    results = list(inferred.values())
    print(f"[ONTOLOGY] entities={len(entity_names)} "
          f"inferred={len(results)} "
          f"skipped_no_corroboration={skipped_no_corroboration}")

    return results
