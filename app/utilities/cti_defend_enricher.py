#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

from rdflib import Graph, RDF, RDFS, Namespace


# ===========================================================
# Load ontology TTL files into RDF graph
# ===========================================================
def load_d3fend_graph(ttl_files):
    g = Graph()
    for ttl in ttl_files:
        try:
            g.parse(str(ttl), format="turtle")
            print(f"[D3FEND] Loaded TTL ontology module: {ttl.name}")
        except Exception as e:
            print(f"[D3FEND] ERROR parsing {ttl}: {e}")
    return g


# ===========================================================
# Extract D3FEND classes
# ===========================================================
def extract_d3fend_classes(graph):
    classes = set()
    D3F = Namespace("http://d3fend.mitre.org/ontologies/d3fend#")

    # Directly defined defensive techniques
    for s in graph.subjects(RDF.type, D3F.DefensiveTechnique):
        classes.add(str(s))

    # Subclasses of DefensiveTechnique
    for s, _, parent in graph.triples((None, RDFS.subClassOf, D3F.DefensiveTechnique)):
        classes.add(str(s))

    print(f"[D3FEND] Defensive techniques discovered: {len(classes)}")
    return classes


# ===========================================================
# Build dynamic STIX → D3FEND type mappings
# ===========================================================
def build_dynamic_mapping(classes):
    def find(keyword):
        keyword = keyword.lower()
        for c in classes:
            if keyword in c.lower():
                return c
        return None

    mapping = {
        "threat-actor": find("actor"),
        "malware": find("malware"),
        "tool": find("tool"),
        "infrastructure": find("artifact"),
        "observed-data": find("behavior"),
        "attack-pattern": find("technique"),
    }

    print("\n[D3FEND] Dynamic STIX → D3FEND Mapping:")
    for stix_type, d3 in mapping.items():
        print(f"  {stix_type:15} → {d3}")

    return mapping


# ===========================================================
# MAIN ENRICHER (Creates CAD graph)
# ===========================================================
def enrich_stix_bundle_with_defend(bundle: dict, defense_root: Path):
    """
    Input:
        STIX bundle (dict), defense ontology root directory

    Output:
        (unchanged_but_annotated_bundle, metadata_info)
    """

    print("[D3FEND] Enriching STIX bundle...")

    # -------------------------------------------------------
    # Scenario narrative (if any)
    # -------------------------------------------------------
    scenario_dir = defense_root.parent.parent.parent / "scenario"
    if scenario_dir.exists():
        print("[D3FEND] Loading scenario narrative...")
        scenario_files = list(scenario_dir.glob("*.scenario.txt"))
        scenario_text = "\n".join(f.read_text() for f in scenario_files) if scenario_files else ""
    else:
        print("[D3FEND] No scenario directory found.")
        scenario_text = ""

    # -------------------------------------------------------
    # Load ontology + schema
    # -------------------------------------------------------
    ontology_dir = defense_root / "ontology"
    cad_schema_file = defense_root / "D3fend_CAD_Graph_Schema.json"

    ontology_modules = []
    for f in ontology_dir.rglob("*"):
        if f.suffix in [".ttl", ".rdf", ".owl"]:
            ontology_modules.append(str(f))

    with cad_schema_file.open("r", encoding="utf-8") as f:
        cad_schema = json.load(f)

    ttl_files = [Path(p) for p in ontology_modules if p.endswith(".ttl")]
    d3f_graph = load_d3fend_graph(ttl_files)

    # Extract namespaces from ontology
    namespaces = {prefix: str(ns) for prefix, ns in d3f_graph.namespaces()}
    D3F = Namespace(namespaces.get("d3f"))
    ATTCK = Namespace(namespaces.get("attack"))
    CAD = Namespace(namespaces.get("cad"))

    # Defensive technique IRIs
    d3f_classes = extract_d3fend_classes(d3f_graph)

    # Mitigation mappings (d3f technique → ATT&CK IRI)
    mitigations = [
        (str(dtech), str(attack))
        for dtech, _, attack in d3f_graph.triples((None, D3F.mitigates, None))
    ]

    # Derived-from hierarchy
    derived_from = [
        (str(child), str(parent))
        for child, _, parent in d3f_graph.triples((None, D3F["derived-from"], None))
    ]

    # -------------------------------------------------------
    # Enrich STIX objects with metadata used by CAD
    # -------------------------------------------------------
    enriched_objects = []
    for obj in bundle.get("objects", []):
        otype = obj.get("type")

        if otype:
            obj.setdefault("labels", [])
            d_label = f"d3f:{otype}"
            if d_label not in obj["labels"]:
                obj["labels"].append(d_label)

            obj["x_d3fend_class"] = d_label

        analytic_id = cad_schema.get("id_namespace", "cad:analytic:") + obj.get("id", "UNKNOWN")
        obj["x_cad_schema"] = {
            "analytic_id": analytic_id,
            "analytic_type": otype,
            "references": obj.get("external_references", []),
        }

        enriched_objects.append(obj)

    bundle["objects"] = enriched_objects

    # -------------------------------------------------------
    # CAD GRAPH GENERATION
    # -------------------------------------------------------
    cad_nodes = []
    cad_edges = []

    # ----------------------------------------------
    # 1. ATT&CK attack patterns (node id = STIX id)
    # ----------------------------------------------
    for obj in enriched_objects:
        if obj.get("type") == "attack-pattern":
            ext_id = None
            for ref in obj.get("external_references", []):
                if "external_id" in ref:
                    ext_id = ref["external_id"]

            cad_nodes.append({
                "id": obj["id"],  # KEY FIX: use STIX ID directly
                "nodeType": "Attack",
                "label": obj.get("name"),
                "properties": {
                    "attack_id": ext_id,
                    "description": obj.get("description", "")
                }
            })

    # ----------------------------------------------
    # 2. Agents (threat actors, malware, tools)
    # ----------------------------------------------
    for obj in enriched_objects:
        if obj.get("type") in ["malware", "tool", "threat-actor"]:
            cad_nodes.append({
                "id": obj["id"],
                "nodeType": "Agent",
                "label": obj.get("name"),
                "properties": {}
            })

    # ----------------------------------------------
    # 3. Observed-data events
    # ----------------------------------------------
    for obj in enriched_objects:
        if obj.get("type") == "observed-data":
            cad_nodes.append({
                "id": obj["id"],
                "nodeType": "Event",
                "label": obj.get("name") or "Observed Behavior",
                "properties": obj
            })

    # ----------------------------------------------
    # 3b. Scenario narrative events
    # ----------------------------------------------
    if scenario_text:
        for line in scenario_text.split("\n"):
            t = line.strip()
            if not t:
                continue
            sid = f"scenario-{abs(hash(t))}"
            cad_nodes.append({
                "id": sid,
                "nodeType": "Event",
                "label": t[:80],
                "properties": {"full_text": t}
            })

    # ----------------------------------------------
    # 4. Countermeasures (D3F techniques)
    # ----------------------------------------------
    for iri in d3f_classes:
        tname = iri.split("#")[-1]
        cad_nodes.append({
            "id": iri,               # Use full IRI for uniqueness
            "nodeType": "Countermeasure",
            "label": tname,
            "properties": {"iri": iri}
        })

    # ----------------------------------------------
    # 5. Analytics
    # ----------------------------------------------
    for dtech, attack in mitigations:
        tname = dtech.split("#")[-1]
        cad_nodes.append({
            "id": f"analytic::{tname}",
            "nodeType": "Analytic",
            "label": f"{tname} Analytic",
            "properties": {
                "analyticImplements": tname,
                "analyticPurpose": f"Mitigates {attack}"
            }
        })

    # ======================================================
    # CAD EDGE CREATION
    # ======================================================

    # ----------------------------------------------
    # Mitigates edges
    # ----------------------------------------------
    for dtech, attack_iri in mitigations:
        tech_id = dtech  # IRI
        attack_tid = attack_iri.split("/")[-1]

        for obj in enriched_objects:
            if obj.get("type") == "attack-pattern":
                for ref in obj.get("external_references", []):
                    if ref.get("external_id") == attack_tid:
                        cad_edges.append({
                            "id": f"mit-{tech_id}-{obj['id']}",
                            "source": tech_id,
                            "target": obj["id"],
                            "relationship": "mitigates"
                        })

    # ----------------------------------------------
    # Derived-from edges
    # ----------------------------------------------
    for child, parent in derived_from:
        cad_edges.append({
            "id": f"der-{child}-{parent}",
            "source": child,
            "target": parent,
            "relationship": "derived-from"
        })

    # ----------------------------------------------
    # Agent uses Attack edges
    # ----------------------------------------------
    for rel in enriched_objects:
        if rel.get("type") != "relationship":
            continue
        if rel.get("relationship_type") != "uses":
            continue

        src = rel.get("source_ref")
        dst = rel.get("target_ref")

        cad_edges.append({
            "id": f"use-{src}-{dst}",
            "source": src,
            "target": dst,
            "relationship": "uses"
        })

    # ----------------------------------------------
    # Attack observed-in Event edges
    # ----------------------------------------------
    attack_ids = {o["id"] for o in enriched_objects if o.get("type") == "attack-pattern"}
    event_ids = {o["id"] for o in enriched_objects if o.get("type") == "observed-data"}

    for a in attack_ids:
        for e in event_ids:
            cad_edges.append({
                "id": f"obs-{a}-{e}",
                "source": a,
                "target": e,
                "relationship": "observed-in"
            })

    # ----------------------------------------------
    # Scenario sequencing edges
    # ----------------------------------------------
    if scenario_text:
        lines = [l.strip() for l in scenario_text.split("\n") if l.strip()]
        for i in range(len(lines) - 1):
            src = f"scenario-{abs(hash(lines[i]))}"
            dst = f"scenario-{abs(hash(lines[i+1]))}"
            cad_edges.append({
                "id": f"seq-{src}-{dst}",
                "source": src,
                "target": dst,
                "relationship": "sequence"
            })

    # ----------------------------------------------
    # Scenario → Attack relationship edges
    # ----------------------------------------------
    if scenario_text:
        for attack_obj in enriched_objects:
            if attack_obj.get("type") != "attack-pattern":
                continue

            attack_name = attack_obj.get("name", "").lower()

            for line in scenario_text.split("\n"):
                if attack_name and attack_name in line.lower():
                    sid = f"scenario-{abs(hash(line.strip()))}"
                    cad_edges.append({
                        "id": f"rel-{sid}-{attack_obj['id']}",
                        "source": sid,
                        "target": attack_obj["id"],
                        "relationship": "related-to"
                    })

    # ======================================================
    # FINAL METADATA + RETURN STRUCTURE
    # ======================================================
    dynamic_map = {
        obj.get("type"): obj.get("x_d3fend_class")
        for obj in enriched_objects if obj.get("type")
    }

    cad_graph = {
        "nodes": cad_nodes,
        "edges": cad_edges,
        "metadata": {
            "source": "blackcat_cti_pipeline",
            "stix_bundle_id": bundle.get("id"),
            "ontology_modules": ontology_modules
        }
    }

    info = {
        "ontology_modules": ontology_modules,
        "cad_schema": str(cad_schema_file),
        "mappings_used": dynamic_map,
        "bundle": bundle,
        "cad_graph": cad_graph
    }

    print(f"[D3FEND] CAD Graph: {len(cad_nodes)} nodes, {len(cad_edges)} edges")

    return bundle, info
