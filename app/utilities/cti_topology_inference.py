"""
cti_topology_inference.py — Stage 4: Range topology inference.

Reads a finalized STIX 2.1 bundle (produced by stage 2 + stage 3) and the
loaded MITRE ATT&CK taxonomy, then emits a custom SDO of type
`x-cti-range-topology` describing the deployable range shape the bundle
implies.

Hard rules (per project memory feedback_no_static_lists_dynamic_only.md):
  - No static malware-name -> OS lookup tables.
  - No hardcoded technique -> infrastructure-role tables.
  - Every output field traces back to an ontology hit: MITRE ATT&CK
    (`x_mitre_platforms`, `kill_chain_phases`, data-component / data-source
    graph), STIX 2.1 open vocabs (`infrastructure-type-ov`,
    `account_type-ov`, `identity-class-ov`, `relationship_type-ov`),
    NLTK/spaCy lexical filters, or YAML data files under
    ``app/utilities/data/`` (data, not code).

Output object (custom STIX SDO):

    {
      "type": "x-cti-range-topology",
      "spec_version": "2.1",
      "id": "x-cti-range-topology--<uuid>",
      "created": "...",
      "modified": "...",
      "primary_platform": "windows" | "linux" | "macos",
      "primary_platform_confidence": float,
      "primary_platform_source": "<provenance string>",
      "derived_from": ["malware--...", "attack-pattern--...", ...],
      "hosts": [
        {
          "name": "range-...",
          "role": "dc" | "workstation" | "exchange" | ...,
          "platform": "windows" | "linux" | ...,
          "os": "<x_cti_os if present>",
          "ip": "<x_cti_ip if present>",
          "image_candidates": [...],
          "services": [...],
          "domain_membership": "<dns_name | NetBIOS>",
          "software_required": [...],
          "member_of": [...],
          "inferred_from": [...]
        }
      ],
      "user_accounts": [
        {
          "username": ..., "account_type": ..., "privilege": ...,
          "domain": ...,
          "ansible_role_input": {"username", "password", "is_admin", "user_tags"}
        }
      ],
      "identities": [
        {"id", "name", "identity_class", "domain_type", "signals"}
      ],
      "networks": [
        {"name": ..., "members": [host_name, ...], "anchor_identity": ...}
      ]
    }
"""

from __future__ import annotations

import re
import uuid
import datetime
import gzip
import json
import os
import socket
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Optional


# ----------------------------------------------------------------------
# STIX 2.1 vocab + relationship-type loading
# ----------------------------------------------------------------------
#
# We pull the relationship_type-ov and infrastructure-type-ov from the
# already-shipped vocab JSON shared with the STIX builder. Refusing to
# hardcode the vocab here mirrors cti_stix_builders.py.

_VOCAB_PATH = Path(__file__).resolve().parent / "data" / "stix_open_vocabs.yml"
_D3FEND_TTL_PATH = (
    Path(__file__).resolve().parent
    / "D3fend_CAD" / "ontology" / "src" / "ontology" / "d3fend-protege.ttl"
)


@lru_cache(maxsize=1)
def _stix_open_vocabs() -> dict:
    """
    Load the STIX 2.1 open-vocab YAML (a thin mirror of the spec's
    OPEN-VOCAB sections, shared with cti_stix_builders.py). Returns
    frozensets per vocab; empty frozensets when the YAML is missing so
    this module never hard-fails.
    """
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(_VOCAB_PATH.read_text(encoding="utf-8")) or {}
        return {
            "infrastructure_type_ov": frozenset(doc.get("infrastructure_type_ov") or []),
            "identity_class_ov":      frozenset(doc.get("identity_class_ov") or []),
            "account_type_ov":        frozenset(doc.get("account_type_ov") or []),
            "relationship_type_ov":   frozenset(doc.get("relationship_type_ov") or []),
        }
    except Exception:
        return {
            "infrastructure_type_ov": frozenset(),
            "identity_class_ov":      frozenset(),
            "account_type_ov":        frozenset(),
            "relationship_type_ov":   frozenset(),
        }


def now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def new_id() -> str:
    return f"x-cti-range-topology--{uuid.uuid4()}"


def _slug(text: str) -> str:
    """RFC 952/1123-ish hostname slug: lowercase, alnum + hyphen, max 40."""
    if not text:
        return "host"
    low = text.strip().lower()
    out = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    return (out[:40] or "host")


def _norm(text: str) -> str:
    """Casefolded slug for equality checks; not length-capped."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")


def _objects_by_id(bundle_objects: list) -> dict:
    return {
        o.get("id"): o for o in bundle_objects
        if isinstance(o, dict) and o.get("id")
    }


def _external_id(obj: dict, source_name: str) -> Optional[str]:
    """Return the first external_id for a STIX external reference source."""
    wanted = (source_name or "").strip().lower()
    for er in obj.get("external_references") or []:
        if (er.get("source_name") or "").strip().lower() == wanted:
            eid = (er.get("external_id") or "").strip()
            if eid:
                return eid
    return None


def _cve_ids_from_obj(obj: dict) -> list:
    """Extract CVE identifiers from vulnerability/software/custom refs."""
    if not isinstance(obj, dict):
        return []
    hits = set()
    for field in ("name", "description"):
        val = obj.get(field)
        if isinstance(val, str):
            hits.update(m.group(0).upper() for m in re.finditer(
                r"CVE-\d{4}-\d{4,7}", val, flags=re.I,
            ))
    for er in obj.get("external_references") or []:
        for field in ("external_id", "source_name", "url", "description"):
            val = er.get(field)
            if isinstance(val, str):
                hits.update(m.group(0).upper() for m in re.finditer(
                    r"CVE-\d{4}-\d{4,7}", val, flags=re.I,
                ))
    for val in obj.get("x_cti_cve_refs") or []:
        if isinstance(val, str):
            hits.update(m.group(0).upper() for m in re.finditer(
                r"CVE-\d{4}-\d{4,7}", val, flags=re.I,
            ))
    return sorted(hits)


# ----------------------------------------------------------------------
# STIX infrastructure graph reachability
# ----------------------------------------------------------------------

_INFRA_GRAPH_RELATIONSHIP_TYPES = frozenset({
    "targets", "uses", "hosts", "consists-of", "delivers", "controls",
})
_ROOT_TYPES = frozenset({"campaign", "intrusion-set", "threat-actor"})


def _infra_graph_relationship_types() -> frozenset:
    """Allowed STIX relationship walk labels, validated against local vocab."""
    vocabs = _stix_open_vocabs()
    known = vocabs.get("relationship_type_ov") or frozenset()
    if not known:
        return _INFRA_GRAPH_RELATIONSHIP_TYPES
    return frozenset(t for t in _INFRA_GRAPH_RELATIONSHIP_TYPES if t in known)


def _relationship_edges(bundle_objects: list,
                        allowed_types: Optional[frozenset] = None) -> list:
    """Return normalized relationship SRO records."""
    allowed = allowed_types
    out = []
    for r in bundle_objects or []:
        if not isinstance(r, dict) or r.get("type") != "relationship":
            continue
        rtype = (r.get("relationship_type") or "").strip().lower()
        if allowed is not None and rtype not in allowed:
            continue
        src = r.get("source_ref")
        tgt = r.get("target_ref")
        if not (src and tgt):
            continue
        out.append({
            "id": r.get("id"),
            "relationship_type": rtype,
            "source_ref": src,
            "target_ref": tgt,
            "description": r.get("description"),
        })
    return out


def _infra_graph_context(bundle_objects: list) -> dict:
    """
    Build the infra-relevant STIX graph and mark infrastructure reachable
    from campaign / intrusion-set / threat-actor roots.
    """
    by_id = _objects_by_id(bundle_objects)
    allowed = _infra_graph_relationship_types()
    edges = _relationship_edges(bundle_objects, allowed)
    adjacency: dict[str, list[dict]] = {}
    for e in edges:
        adjacency.setdefault(e["source_ref"], []).append(e)
        adjacency.setdefault(e["target_ref"], []).append(e)

    roots = sorted(
        oid for oid, obj in by_id.items()
        if obj.get("type") in _ROOT_TYPES
    )
    reachable = set(roots)
    q = deque(roots)
    while q:
        cur = q.popleft()
        for e in adjacency.get(cur, []):
            nxt = e["target_ref"] if e["source_ref"] == cur else e["source_ref"]
            if nxt in reachable:
                continue
            reachable.add(nxt)
            q.append(nxt)

    infra_ids = {
        oid for oid, obj in by_id.items()
        if obj.get("type") == "infrastructure"
    }
    return {
        "root_refs": roots,
        "allowed_relationship_types": sorted(allowed),
        "edges": edges,
        "reachable_refs": sorted(reachable),
        "reachable_infrastructure_refs": sorted(infra_ids & reachable),
    }


def _edges_touching(ref_id: str, graph_ctx: dict) -> list:
    if not ref_id:
        return []
    out = []
    for e in graph_ctx.get("edges") or []:
        if ref_id in (e.get("source_ref"), e.get("target_ref")):
            out.append(dict(e))
    return out


# ----------------------------------------------------------------------
# Network-traffic SCO -> service inference
# ----------------------------------------------------------------------

def _transport_protocols(protocols: list) -> list:
    """Keep protocol names socket.getservbyport can resolve."""
    out = []
    for p in protocols or []:
        proto = str(p).strip().lower()
        if proto in ("tcp", "udp"):
            out.append(proto)
    return out


@lru_cache(maxsize=2048)
def _iana_service_name(port: int, proto: str) -> Optional[str]:
    """
    Resolve (port, protocol) through the platform IANA services database.
    The optional iana-port-numbers package is intentionally not required;
    socket.getservbyport uses the shipped services database and keeps this
    dependency-free.
    """
    try:
        return socket.getservbyport(int(port), proto)
    except Exception:
        return None


def _network_service_records(nt: dict) -> list:
    """Translate a network-traffic SCO into service records."""
    if not isinstance(nt, dict):
        return []
    protocols = _transport_protocols(nt.get("protocols") or [])
    if not protocols:
        # Try both transports when the SCO gives a port but omits the
        # transport layer. Only successful IANA resolutions survive.
        protocols = ["tcp", "udp"]

    out = []
    for port_key in ("dst_port", "src_port"):
        port = nt.get(port_key)
        if port is None:
            continue
        try:
            port_int = int(port)
        except (TypeError, ValueError):
            continue
        for proto in protocols:
            iana = _iana_service_name(port_int, proto)
            if not iana:
                continue
            out.append({
                "service": _slug(iana),
                "iana_name": iana,
                "port": port_int,
                "protocol": proto,
                "direction": "dst" if port_key == "dst_port" else "src",
                "stix_id": nt.get("id"),
                "source": "network-traffic SCO port/protocol resolved via socket.getservbyport",
            })
    # Deduplicate by port/protocol/name/direction.
    seen = set()
    deduped = []
    for rec in out:
        key = (rec["service"], rec["port"], rec["protocol"], rec["direction"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
    return deduped


def _observable_memberships(bundle_objects: list) -> dict:
    """
    observed-data.object_refs binds SCOs together. Return
    {member_ref: set(peer_refs)} for direct co-membership.
    """
    peers: dict[str, set[str]] = {}
    for o in bundle_objects or []:
        if not isinstance(o, dict) or o.get("type") != "observed-data":
            continue
        refs = [r for r in (o.get("object_refs") or []) if isinstance(r, str)]
        for ref in refs:
            others = {r for r in refs if r != ref}
            if others:
                peers.setdefault(ref, set()).update(others)
    return peers


def _network_services_by_infrastructure(bundle_objects: list) -> tuple[dict, list]:
    """
    Return ({infrastructure-id: [network service records]}, network_edges).
    Direct relationship/observed-data membership wins. If a bundle has one
    infrastructure SDO and unanchored traffic, attach it to that host as the
    least-surprising one-report topology.
    """
    by_id = _objects_by_id(bundle_objects)
    infra_ids = {
        oid for oid, obj in by_id.items()
        if obj.get("type") == "infrastructure"
    }
    network_ids = [
        oid for oid, obj in by_id.items()
        if obj.get("type") == "network-traffic"
    ]
    memberships = _observable_memberships(bundle_objects)
    all_relationships = _relationship_edges(bundle_objects, None)

    by_infra: dict[str, list[dict]] = {}
    network_edges = []

    for nt_id in network_ids:
        nt = by_id[nt_id]
        services = _network_service_records(nt)
        if not services:
            continue

        anchors = set()
        for e in all_relationships:
            if nt_id not in (e["source_ref"], e["target_ref"]):
                continue
            other = e["target_ref"] if e["source_ref"] == nt_id else e["source_ref"]
            if other in infra_ids:
                anchors.add(other)
        anchors.update(r for r in memberships.get(nt_id, set()) if r in infra_ids)
        if not anchors and len(infra_ids) == 1:
            anchors.update(infra_ids)

        for rec in services:
            network_edges.append({
                "source_ref": nt.get("src_ref"),
                "target_ref": nt.get("dst_ref"),
                "protocol": rec["protocol"],
                "port": rec["port"],
                "service": rec["service"],
                "network_traffic_ref": nt_id,
                "host_refs": sorted(anchors),
            })

        for inf_id in anchors:
            by_infra.setdefault(inf_id, []).extend(services)

    for inf_id, recs in list(by_infra.items()):
        seen = set()
        deduped = []
        for rec in recs:
            key = (rec["service"], rec["port"], rec["protocol"], rec["direction"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(dict(rec))
        by_infra[inf_id] = deduped
    return by_infra, network_edges


# ----------------------------------------------------------------------
# Software / vulnerability inventory
# ----------------------------------------------------------------------

def _software_record(sw: dict) -> dict:
    out = {
        "name": sw.get("name"),
        "version": sw.get("version"),
        "vendor": sw.get("vendor"),
        "cpe": sw.get("cpe"),
        "swid": sw.get("swid"),
        "purl": sw.get("x_cti_purl"),
        "software_kind": sw.get("x_cti_software_kind"),
        "cve_refs": _cve_ids_from_obj(sw),
        "stix_id": sw.get("id"),
        "source": "software SCO",
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _direct_refs_by_type(ref_id: str, bundle_objects: list,
                         target_type: str) -> set:
    by_id = _objects_by_id(bundle_objects)
    hits = set()
    for e in _relationship_edges(bundle_objects, None):
        if ref_id not in (e["source_ref"], e["target_ref"]):
            continue
        other = e["target_ref"] if e["source_ref"] == ref_id else e["source_ref"]
        if by_id.get(other, {}).get("type") == target_type:
            hits.add(other)
    for peer in _observable_memberships(bundle_objects).get(ref_id, set()):
        if by_id.get(peer, {}).get("type") == target_type:
            hits.add(peer)
    return hits


def _software_inventory_by_infrastructure(bundle_objects: list) -> dict:
    by_id = _objects_by_id(bundle_objects)
    infra_ids = [
        oid for oid, obj in by_id.items()
        if obj.get("type") == "infrastructure"
    ]
    software_ids = [
        oid for oid, obj in by_id.items()
        if obj.get("type") == "software"
    ]
    out: dict[str, list[dict]] = {}
    for inf_id in infra_ids:
        linked = _direct_refs_by_type(inf_id, bundle_objects, "software")
        if not linked and len(infra_ids) == 1:
            # A single-host bundle with unlinked software is a common
            # extraction artifact. Treat the software inventory as host
            # inventory, but keep provenance explicit.
            linked = set(software_ids)
        for sw_id in linked:
            rec = _software_record(by_id[sw_id])
            rec["source"] = "software SCO linked to infrastructure"
            out.setdefault(inf_id, []).append(rec)
    return out


def _candidate_nvd_dirs() -> list[Path]:
    paths = []
    for env_key in ("CTI_NVD_CACHE", "NVD_JSON_DIR", "NVD_CACHE_DIR"):
        val = os.environ.get(env_key)
        if val:
            paths.append(Path(val).expanduser())
    here = Path(__file__).resolve().parent
    paths.extend([
        here / "data" / "nvd",
        here / "data" / "nvd-cache",
        Path.home() / ".cache" / "nvd",
    ])
    return paths


def _walk_cpe_matches(node) -> list[str]:
    """Extract vulnerable CPE criteria from NVD 1.1/2.0 config nodes."""
    cpes = []
    if isinstance(node, dict):
        for key in ("cpe_match", "cpeMatch"):
            for match in node.get(key) or []:
                if not isinstance(match, dict):
                    continue
                if match.get("vulnerable") is False:
                    continue
                criteria = match.get("criteria") or match.get("cpe23Uri")
                if criteria:
                    cpes.append(criteria)
        for child_key in ("nodes", "children"):
            for child in node.get(child_key) or []:
                cpes.extend(_walk_cpe_matches(child))
    elif isinstance(node, list):
        for child in node:
            cpes.extend(_walk_cpe_matches(child))
    return cpes


def _cve_id_from_nvd_item(item: dict) -> Optional[str]:
    cve = item.get("cve") if isinstance(item, dict) else None
    if isinstance(cve, dict):
        meta = cve.get("CVE_data_meta")
        if isinstance(meta, dict) and meta.get("ID"):
            return str(meta["ID"]).upper()
        if cve.get("id"):
            return str(cve["id"]).upper()
    if item.get("id"):
        return str(item["id"]).upper()
    return None


@lru_cache(maxsize=1)
def _local_nvd_cpe_index() -> dict:
    """
    Build {CVE-ID: [CPE 2.3 strings]} from local NVD JSON cache files.
    No network access is attempted.
    """
    files = []
    for root in _candidate_nvd_dirs():
        if not root.is_dir():
            continue
        files.extend(root.glob("*.json"))
        files.extend(root.glob("*.json.gz"))
    index: dict[str, list[str]] = {}
    for path in sorted(set(files)):
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    doc = json.load(fh)
            else:
                doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = doc.get("vulnerabilities")
        if items is None:
            items = doc.get("CVE_Items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cve_id = _cve_id_from_nvd_item(item)
            if not cve_id:
                continue
            cve_payload = item.get("cve") if isinstance(item.get("cve"), dict) else {}
            configs = (
                item.get("configurations")
                or cve_payload.get("configurations")
                or {}
            )
            cpes = _walk_cpe_matches(configs)
            if cpes:
                index.setdefault(cve_id, [])
                for cpe in cpes:
                    if cpe not in index[cve_id]:
                        index[cve_id].append(cpe)
    return index


def _software_hint_from_cpe(cpe: str) -> dict:
    parts = str(cpe).split(":")
    # cpe:2.3:a:vendor:product:version:...
    hint = {"cpe": cpe}
    if len(parts) > 5:
        vendor = parts[3].replace("\\", "")
        product = parts[4].replace("\\", "")
        version = parts[5].replace("\\", "")
        if vendor and vendor != "*":
            hint["vendor"] = vendor
        if product and product != "*":
            hint["name"] = product.replace("_", " ")
        if version and version != "*":
            hint["version"] = version
    return hint


def _vulnerabilities_by_infrastructure(bundle_objects: list) -> dict:
    by_id = _objects_by_id(bundle_objects)
    infra_ids = [
        oid for oid, obj in by_id.items()
        if obj.get("type") == "infrastructure"
    ]
    vuln_ids = [
        oid for oid, obj in by_id.items()
        if obj.get("type") == "vulnerability"
    ]
    nvd = _local_nvd_cpe_index()
    out: dict[str, list[dict]] = {}
    for inf_id in infra_ids:
        linked = _direct_refs_by_type(inf_id, bundle_objects, "vulnerability")
        if not linked and len(infra_ids) == 1:
            linked = set(vuln_ids)
        for vuln_id in linked:
            vuln = by_id[vuln_id]
            cves = _cve_ids_from_obj(vuln)
            if not cves and vuln.get("name"):
                cves = [vuln["name"]]
            for cve in cves:
                cpes = nvd.get(cve.upper(), [])
                rec = {
                    "cve": cve.upper(),
                    "stix_id": vuln_id,
                    "cpe_matches": cpes,
                    "software_hints": [_software_hint_from_cpe(c) for c in cpes],
                    "source": "vulnerability SDO linked to infrastructure",
                }
                out.setdefault(inf_id, []).append(rec)
    return out


# ----------------------------------------------------------------------
# ATT&CK platform / telemetry / artifact surface
# ----------------------------------------------------------------------

def _attack_surface_from_techniques(bundle_objects: list, taxonomy: dict) -> dict:
    idx = (taxonomy or {}).get("attack_id_index", {}) or {}
    dc_index = _datacomponent_index(taxonomy) if taxonomy else {}
    techniques = []
    platforms = set()
    permissions = set()
    data_sources = set()
    data_components = set()
    tactics = set()
    artifacts = set()
    d3fend_index = _d3fend_technique_artifact_index()
    d3fend_artifacts = set()
    for tid in _technique_ids_in_bundle(bundle_objects):
        tax_obj = idx.get(tid)
        if not tax_obj:
            continue
        tech_platforms = sorted({
            str(p).strip() for p in tax_obj.get("x_mitre_platforms") or []
            if str(p).strip()
        })
        tech_perms = sorted({
            str(p).strip() for p in tax_obj.get("x_mitre_permissions_required") or []
            if str(p).strip()
        })
        tech_tactics = sorted({
            kc.get("phase_name") for kc in tax_obj.get("kill_chain_phases") or []
            if kc.get("phase_name")
        })
        signals = dc_index.get(tid, {})
        tech_ds = sorted({
            str(d).strip() for d in signals.get("data_sources", set())
            if str(d).strip()
        })
        tech_dc = sorted({
            str(d).strip() for d in signals.get("data_components", set())
            if str(d).strip()
        })
        # Legacy ATT&CK bundles may still carry x_mitre_data_sources.
        for ds in tax_obj.get("x_mitre_data_sources") or []:
            ds_s = str(ds).strip()
            if ds_s:
                tech_ds.append(ds_s.split(":", 1)[0].strip())
                tech_dc.append(ds_s)
        platforms.update(tech_platforms)
        permissions.update(tech_perms)
        tactics.update(tech_tactics)
        data_sources.update(tech_ds)
        data_components.update(tech_dc)
        artifacts.update(_slug(dc) for dc in tech_dc if dc)
        tech_d3fend = d3fend_index.get(tid, [])
        d3fend_artifacts.update(tech_d3fend)
        techniques.append({
            "technique_id": tid,
            "name": tax_obj.get("name"),
            "platforms": tech_platforms,
            "required_permissions": tech_perms,
            "tactics": tech_tactics,
            "data_sources": sorted(set(tech_ds)),
            "data_components": sorted(set(tech_dc)),
            "digital_artifacts": sorted({_slug(dc) for dc in tech_dc if dc}),
            "d3fend_artifacts": tech_d3fend,
        })
    return {
        "techniques": techniques,
        "platforms": sorted(platforms),
        "required_permissions": sorted(permissions),
        "data_sources": sorted(data_sources),
        "data_components": sorted(data_components),
        "digital_artifacts": sorted(artifacts),
        "d3fend_artifacts": sorted(d3fend_artifacts),
        "tactics": sorted(tactics),
        "source": "MITRE ATT&CK taxonomy x_mitre_platforms, x_mitre_permissions_required, detection data-source graph; D3FEND local ontology owl:someValuesFrom artifact restrictions",
    }


@lru_cache(maxsize=1)
def _d3fend_technique_artifact_index() -> dict:
    """
    Parse the local D3FEND TTL ontology for ATT&CK technique blocks and
    the digital artifacts they access/modify/produce via OWL restrictions.
    """
    if not _D3FEND_TTL_PATH.is_file():
        return {}
    try:
        text = _D3FEND_TTL_PATH.read_text(encoding="utf-8")
    except Exception:
        return {}

    index: dict[str, list[str]] = {}
    block_re = re.compile(
        r"\n:(T\d{4}(?:\.\d{3})?)\s+a\s+owl:Class\s*;(?P<body>.*?)(?=\n\n:|\Z)",
        re.S,
    )
    for m in block_re.finditer(text):
        tid = m.group(1).upper()
        body = m.group("body")
        artifacts = sorted({
            _slug(name)
            for name in re.findall(r"owl:someValuesFrom\s+:([A-Za-z][A-Za-z0-9_-]+)", body)
            if name and not name.startswith("T")
        })
        if artifacts:
            index[tid] = artifacts
    return index


# ----------------------------------------------------------------------
# Dynamic STIX-vocab -> range-role mapping
# ----------------------------------------------------------------------
#
# Earlier revisions of this file kept a small static dictionary mapping
# `infrastructure-type-ov` terms onto range-host roles. That violated the
# "no static vocabulary lists" rule. We now derive the mapping at runtime
# from the STIX 2.1 `infrastructure-type-ov` itself: each vocab term is
# its own role slug. Where the STIX term is a known synonym (e.g.,
# `workstation` -> `workstation`, `routers-switches` -> `network-device`),
# we slugify by removing connective words ("and", "or") and dropping
# trailing plurals — pure string normalisation, not a lookup table.

def _role_from_infra_types(types: list) -> str:
    """
    Reduce STIX 2.1 `infrastructure_types` to a single role slug. We
    return the first vocab term unchanged (slugified) — downstream
    consumers (the range plugin) accept any slug; the names match the
    spec's open vocab, so a custom range-role registry can be data-only.
    """
    if not types:
        return "unknown"
    first = str(types[0]).strip().lower()
    if not first:
        return "unknown"
    # Normalise per RFC 1123 hostname rules so it slots into ansible host
    # groups without further mangling.
    slug = re.sub(r"[^a-z0-9]+", "-", first).strip("-")
    return slug or "unknown"


# ----------------------------------------------------------------------
# Platform aggregation
# ----------------------------------------------------------------------

def _platforms_from_malware(bundle_objects: list) -> tuple:
    """
    Tally `x_mitre_platforms` across all malware objects in the bundle.

    Returns ({platform_name: count}, [stix-ids that contributed]).
    """
    counts = {}
    refs = []
    for o in bundle_objects:
        if o.get("type") != "malware":
            continue
        platforms = o.get("x_mitre_platforms") or []
        for p in platforms:
            key = p.strip().lower()
            counts[key] = counts.get(key, 0) + 1
        if platforms:
            refs.append(o["id"])
    return counts, refs


def _platforms_from_attack_patterns(bundle_objects: list, taxonomy: dict) -> tuple:
    """Tally `x_mitre_platforms` across all attack-patterns via taxonomy index."""
    counts = {}
    refs = []
    idx = (taxonomy or {}).get("attack_id_index", {}) or {}
    for o in bundle_objects:
        if o.get("type") != "attack-pattern":
            continue
        tid = None
        for er in o.get("external_references", []):
            if er.get("source_name") == "mitre-attack":
                tid = er.get("external_id")
                break
        if not tid:
            continue
        tax_obj = idx.get(tid.upper().strip())
        if not tax_obj:
            continue
        platforms = tax_obj.get("x_mitre_platforms") or []
        for p in platforms:
            key = p.strip().lower()
            counts[key] = counts.get(key, 0) + 1
        if platforms:
            refs.append(o["id"])
    return counts, refs


def aggregate_target_platforms(bundle_objects: list, taxonomy: dict) -> dict:
    """
    Aggregate target-platform votes across the bundle. Two signal sources:
      - malware.x_mitre_platforms (weight 3, per-family)
      - attack-pattern.x_mitre_platforms (weight 1, per-technique)
    Both come from ATT&CK ontology — no static seed tables.
    """
    mal_counts, mal_refs = _platforms_from_malware(bundle_objects)
    ap_counts,  ap_refs  = _platforms_from_attack_patterns(bundle_objects, taxonomy)

    tally = {}
    for k, v in mal_counts.items():
        tally[k] = tally.get(k, 0) + v * 3
    for k, v in ap_counts.items():
        tally[k] = tally.get(k, 0) + v

    primary = None
    primary_conf = 0.0
    if tally:
        primary = max(tally, key=tally.get)
        total = sum(tally.values())
        primary_conf = tally[primary] / total if total else 0.0

    provenance_parts = []
    if mal_counts:
        provenance_parts.append(
            f"malware.x_mitre_platforms aggregate ({sum(mal_counts.values())} votes from "
            f"{len(mal_refs)} families)"
        )
    if ap_counts:
        provenance_parts.append(
            f"attack-pattern.x_mitre_platforms via attack_id_index "
            f"({sum(ap_counts.values())} votes from {len(ap_refs)} techniques)"
        )

    return {
        "tally": tally,
        "primary": primary,
        "primary_confidence": round(primary_conf, 3),
        "derived_from": mal_refs + ap_refs,
        "provenance": "; ".join(provenance_parts) or "no platform signals in bundle",
    }


# ----------------------------------------------------------------------
# Service-name discovery from ATT&CK data-component graph
# ----------------------------------------------------------------------
#
# A "service" in the range topology is a logical operating-system service
# (e.g. "active-directory-domain-services", "remote-desktop-services") the
# host must run. We derive it dynamically:
#
#   attack-pattern  <-(detects)-  x-mitre-detection-strategy
#     -(x_mitre_analytic_refs)->  x-mitre-analytic
#     -(x_mitre_log_source_references[].x_mitre_data_component_ref)->
#       x-mitre-data-component
#     -(x_mitre_data_source_ref)-> x-mitre-data-source
#
# The data-component / data-source NAMES are then slugified into service
# tokens. Example: "Active Directory Object Access" -> the host clearly
# offers Active Directory ("active-directory"). The grouping is by the
# leading proper-noun phrase, taken straight from the ontology — no
# technique->service table here.


def _datacomponent_index(taxonomy: dict) -> dict:
    """
    Build a per-technique ATT&CK signal index:

        {technique_id: {"data_components": set[str], "data_sources": set[str]}}

    Walks detection-strategies and analytics in the loaded ATT&CK bundle
    rather than relying on the (now removed in ATT&CK 17.x)
    `x_mitre_data_sources` field on attack-patterns directly. Cached per
    taxonomy id() so this is paid once per Python process.
    """
    if not taxonomy:
        return {}
    cache = taxonomy.get("_topology_datacomponent_index")
    if cache is not None:
        return cache

    bundle_objs = taxonomy.get("_raw_objects")
    if bundle_objs is None:
        # Re-load if the taxonomy doesn't carry raw objects (legacy callers).
        try:
            from .cti_taxonomy_loader import load_mitre_bundle
            bundle_objs = load_mitre_bundle().get("objects", [])
        except Exception:
            bundle_objs = []

    by_id = {o["id"]: o for o in bundle_objs if isinstance(o, dict) and o.get("id")}

    # Collect the canonical set of ATT&CK data-source names (proper-noun
    # phrases such as "Active Directory", "Network Traffic"). The
    # data-component names follow the convention "<DataSource>
    # <SpecificComponent>" (per https://attack.mitre.org/datasources/),
    # so prefix-matching a data-component name against this set yields
    # the data-source. The set is built from the ontology, NOT hardcoded.
    ds_name_set = set()
    for o in bundle_objs:
        if o.get("type") == "x-mitre-data-source":
            nm = (o.get("name") or "").strip()
            if nm:
                ds_name_set.add(nm)

    def _resolve_ds_name(component_name: str) -> Optional[str]:
        """
        Return the canonical data-source name that prefixes the given
        data-component name, or None if no ontology match.
        """
        if not component_name:
            return None
        # Longest-prefix match against the data-source name set.
        # ("Network Traffic Content" -> "Network Traffic", not "Network".)
        candidate = None
        for ds in ds_name_set:
            if component_name == ds or component_name.startswith(ds + " "):
                if candidate is None or len(ds) > len(candidate):
                    candidate = ds
        return candidate

    # x-mitre-data-component -> data-source name (via x_mitre_data_source_ref
    # when present; otherwise fall back to ontology prefix match).
    dc_to_ds_name = {}
    for o in bundle_objs:
        if o.get("type") != "x-mitre-data-component":
            continue
        ds_ref = o.get("x_mitre_data_source_ref")
        ds_name = None
        if ds_ref:
            ds = by_id.get(ds_ref)
            if ds:
                ds_name = ds.get("name")
        if not ds_name:
            ds_name = _resolve_ds_name((o.get("name") or "").strip())
        if ds_name:
            dc_to_ds_name[o["id"]] = ds_name

    # detection-strategy -> {data_component names, data_source names}
    det_signals = {}
    for o in bundle_objs:
        if o.get("type") != "x-mitre-detection-strategy":
            continue
        dcs = set()
        dss = set()
        for ana_id in o.get("x_mitre_analytic_refs", []) or []:
            ana = by_id.get(ana_id)
            if not ana:
                continue
            for log in ana.get("x_mitre_log_source_references", []) or []:
                dc_id = log.get("x_mitre_data_component_ref")
                dc = by_id.get(dc_id)
                if dc and dc.get("name"):
                    dcs.add(dc["name"])
                    if dc_id in dc_to_ds_name:
                        dss.add(dc_to_ds_name[dc_id])
        det_signals[o["id"]] = (dcs, dss)

    # Walk relationships: (detects, det-strategy) -> attack-pattern.
    # Build technique-id -> aggregated signal set.
    tech_signals = {}
    for r in bundle_objs:
        if r.get("type") != "relationship":
            continue
        if r.get("relationship_type") != "detects":
            continue
        src = r.get("source_ref") or ""
        tgt = r.get("target_ref") or ""
        if not src.startswith("x-mitre-detection-strategy--"):
            continue
        if not tgt.startswith("attack-pattern--"):
            continue
        ap = by_id.get(tgt)
        if not ap:
            continue
        tid = None
        for er in ap.get("external_references", []) or []:
            if er.get("source_name") == "mitre-attack":
                tid = (er.get("external_id") or "").upper().strip()
                break
        if not tid:
            continue
        dcs, dss = det_signals.get(src, (set(), set()))
        entry = tech_signals.setdefault(
            tid, {"data_components": set(), "data_sources": set()}
        )
        entry["data_components"].update(dcs)
        entry["data_sources"].update(dss)

    taxonomy["_topology_datacomponent_index"] = tech_signals
    return tech_signals


def _service_tokens_from_signals(signals: dict) -> list:
    """
    Convert {data_components, data_sources} sets into a deduplicated
    list of service slug tokens. The token comes straight from ATT&CK
    data-source / data-component names, slugified. We deliberately do
    NOT translate "Active Directory" -> "active-directory-domain-services"
    via a table — `_slug()` produces "active-directory", which the range
    plugin's role registry can resolve. Any downstream alias mapping
    lives in `plugins/range/conf/*.yml`, not here.
    """
    out = set()
    for ds in signals.get("data_sources", []) or []:
        slug = _slug(ds)
        if slug and slug != "host":
            out.add(slug)
    return sorted(out)


def _technique_ids_in_bundle(bundle_objects: list) -> list:
    """Return all ATT&CK technique IDs referenced in the bundle."""
    ids = []
    for o in bundle_objects:
        if o.get("type") != "attack-pattern":
            continue
        for er in o.get("external_references", []):
            if er.get("source_name") == "mitre-attack":
                tid = (er.get("external_id") or "").upper().strip()
                if tid:
                    ids.append(tid)
    return ids


# ----------------------------------------------------------------------
# Active Directory implicating techniques (runtime ontology lookup)
# ----------------------------------------------------------------------
#
# An AD-implicating technique is one whose ATT&CK ontology entry clearly
# tells us the adversary's environment had a Domain Controller. Two
# ontology signals (both checked at runtime against the loaded taxonomy
# — no static technique-to-host table):
#
#   1. `x_mitre_data_sources` contains "Active Directory" OR the
#      "User Account: Domain Account" data-component string. ATT&CK uses
#      "<DataSource>: <DataComponent>" formatting, so any data-source
#      string starting with "Active Directory" counts.
#   2. The technique's name regex-matches /(?:domain|directory|kerberos|
#      active directory)/i AND its tactic (kill_chain_phases phase_name)
#      is in {credential-access, lateral-movement, discovery}. The
#      tactic filter drops false positives like T1583.001 "Acquire
#      Infrastructure: Domains" (resource-development).

_AD_NAME_RE = re.compile(r"(?:domain|directory|kerberos|active directory)", re.I)
_AD_TACTIC_GATE = frozenset({"credential-access", "lateral-movement", "discovery"})


def _technique_implicates_ad(tax_obj: dict) -> bool:
    """
    Decide whether an ATT&CK attack-pattern object implies the presence
    of an Active Directory Domain Controller in the adversary's
    environment. Purely ontology-driven — no hardcoded technique list.
    """
    if not tax_obj:
        return False

    # Signal 1 — x_mitre_data_sources mentions Active Directory or a
    # Domain Account data component.
    data_sources = tax_obj.get("x_mitre_data_sources") or []
    for ds in data_sources:
        s = str(ds)
        # ATT&CK strings are "<DataSource>: <Component>" — match either
        # the bare "Active Directory" data-source or the explicit
        # "User Account: Domain Account" component.
        if s.startswith("Active Directory") or "Active Directory" in s:
            return True
        if "Domain Account" in s:
            return True

    # Signal 2 — name regex + tactic membership.
    name = (tax_obj.get("name") or "").strip()
    if name and _AD_NAME_RE.search(name):
        for kc in tax_obj.get("kill_chain_phases") or []:
            phase = (kc.get("phase_name") or "").strip().lower()
            if phase in _AD_TACTIC_GATE:
                return True

    return False


def _ad_implicating_technique_ids(bundle_objects: list, taxonomy: dict) -> list:
    """
    Walk attack-pattern SDOs in the bundle, resolve each technique-id
    via `taxonomy["attack_id_index"]`, and return the subset whose
    ontology entries implicate Active Directory presence.

    Pure ontology lookup — the set is rebuilt every call from whatever
    is in the bundle and the taxonomy index. No state, no static map.
    """
    if not bundle_objects:
        return []
    idx = (taxonomy or {}).get("attack_id_index", {}) or {}
    out = []
    seen = set()
    for o in bundle_objects:
        if o.get("type") != "attack-pattern":
            continue
        tid = None
        for er in o.get("external_references", []) or []:
            if er.get("source_name") == "mitre-attack":
                tid = (er.get("external_id") or "").upper().strip()
                if tid:
                    break
        if not tid or tid in seen:
            continue
        seen.add(tid)
        tax_obj = idx.get(tid)
        if _technique_implicates_ad(tax_obj):
            out.append(tid)
    return out


def _has_dc_infrastructure(bundle_objects: list, hosts: list) -> bool:
    """
    True iff the bundle's infrastructure SDOs (or the already-derived
    hosts list) include an entry whose role mentions a domain
    controller. Matches "dc" as a token and "domain controller" as a
    phrase, case-insensitive, on:
      - `infrastructure.x_cti_role`
      - `infrastructure.infrastructure_types[]`
      - host['role'] in already-derived hosts.
    """
    def _role_says_dc(role: str) -> bool:
        if not role:
            return False
        low = role.strip().lower()
        if "domain controller" in low:
            return True
        return any(tok == "dc" for tok in re.split(r"[^a-z0-9]+", low) if tok)

    for o in bundle_objects:
        if o.get("type") != "infrastructure":
            continue
        if _role_says_dc(o.get("x_cti_role") or ""):
            return True
        for t in o.get("infrastructure_types") or []:
            if _role_says_dc(str(t)):
                return True
    for h in hosts or []:
        if _role_says_dc(h.get("role") or ""):
            return True
    return False


def _ad_services_from_techniques(bundle_objects: list, taxonomy: dict,
                                 ad_tids: list) -> list:
    """
    Collect AD-relevant service slugs from the data-sources of the
    AD-implicating techniques only. We slugify the data-source name,
    keeping only tokens that are AD-pertinent (any data source
    containing "Active Directory", a "Domain Account" component, or
    the always-present "kerberos"/"dns" prerequisites a DC must run).

    A DC always runs AD DS + Kerberos + DNS — those three are universal
    to every AD deployment per the AD architecture itself, NOT a
    technique-specific table. We add them when at least one ontology
    signal said "AD".
    """
    if not ad_tids:
        return []
    idx = (taxonomy or {}).get("attack_id_index", {}) or {}
    services = set()
    for tid in ad_tids:
        tax_obj = idx.get(tid)
        if not tax_obj:
            continue
        for ds in tax_obj.get("x_mitre_data_sources") or []:
            s = str(ds)
            if "Active Directory" in s or "Domain Account" in s:
                # Slug down to the bare AD service slug.
                services.add("active-directory-domain-services")
    if services:
        services.add("kerberos")
        services.add("dns")
    return sorted(services)


# ----------------------------------------------------------------------
# Identity / domain helpers
# ----------------------------------------------------------------------

def _ad_identities(bundle_objects: list) -> list:
    """
    Return identity SDOs in the bundle that look like Active Directory
    domains. Two signals (in priority order):
      1. `x_cti_domain_type == "active-directory"` (set by make_identity).
      2. `identity_class == "organization"` AND a `x_cti_signals` list
         containing any T-number ATT&CK technique id.
    """
    out = []
    for o in bundle_objects:
        if o.get("type") != "identity":
            continue
        if (o.get("x_cti_domain_type") or "").lower() == "active-directory":
            out.append(o)
            continue
        iclass = (o.get("identity_class") or "").lower()
        signals = o.get("x_cti_signals") or []
        if iclass == "organization" and signals:
            out.append(o)
    return out


def _domain_from_located_at(src_id: str, bundle_objects: list,
                            identity_index: dict) -> Optional[dict]:
    """
    For a STIX object id, walk `located-at` relationships and return the
    first identity SDO it resolves to (or None).
    """
    for r in bundle_objects:
        if r.get("type") != "relationship":
            continue
        if (r.get("relationship_type") or "") != "located-at":
            continue
        if r.get("source_ref") != src_id:
            continue
        tgt = r.get("target_ref") or ""
        if tgt.startswith("identity--"):
            return identity_index.get(tgt)
    return None


# ----------------------------------------------------------------------
# Host shape from infrastructure SDOs
# ----------------------------------------------------------------------

def _image_candidates_for_platform(platform: str, images_catalog: list) -> list:
    """Pure dictionary intersection — no static name lookup."""
    if not (platform and images_catalog):
        return []
    p = platform.strip().lower()
    out = []
    for img in images_catalog:
        img_os = (img.get("os") or "").strip().lower()
        if img_os == p:
            out.append(img.get("name"))
    return out


def _tools_for_platform(bundle_objects: list, platform: str) -> list:
    """
    Return [{name, id}] for every STIX tool SDO whose
    `x_mitre_platforms` includes the host platform (case-insensitive).
    Pure ontology read — tool platforms come from ATT&CK's tool index,
    set by stage 2's make_tool() via the taxonomy lookup.
    """
    if not platform:
        return []
    p = platform.strip().lower()
    out = []
    seen = set()
    for o in bundle_objects:
        if o.get("type") != "tool":
            continue
        plats = [str(x).lower() for x in (o.get("x_mitre_platforms") or [])]
        # Some bundles double-prefixed the field (`x_x_cti_*` etc.); accept
        # the canonical name OR any platform list field stage 2 may add.
        if not plats:
            plats = [str(x).lower() for x in (o.get("x_x_cti_platforms") or [])]
        if not plats:
            continue
        if p in plats:
            name = (o.get("name") or "").strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append({"name": name, "id": o.get("id")})
    return out


def _co_techniques_for_infrastructure(inf_id: str, bundle_objects: list) -> list:
    """
    Return ATT&CK technique IDs that co-occur with an infrastructure SDO
    in the bundle, via relationships of any direction. The set narrows
    the data-component lookup to those techniques actually present in
    this report.
    """
    ap_ids = set()
    for r in bundle_objects:
        if r.get("type") != "relationship":
            continue
        s, t = r.get("source_ref") or "", r.get("target_ref") or ""
        if inf_id not in (s, t):
            continue
        other = t if s == inf_id else s
        if other.startswith("attack-pattern--"):
            ap_ids.add(other)
    # Convert ap IDs to technique-IDs by scanning bundle objects
    out = []
    for o in bundle_objects:
        if o.get("type") != "attack-pattern" or o.get("id") not in ap_ids:
            continue
        for er in o.get("external_references", []):
            if er.get("source_name") == "mitre-attack":
                tid = (er.get("external_id") or "").upper().strip()
                if tid:
                    out.append(tid)
    return out


def _looks_like_hostname_token(name: str) -> bool:
    name = (name or "").strip()
    if not name:
        return False
    if len(name) <= 4 and name.upper() == name:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", name))


def derive_hosts(bundle_objects: list, primary_platform: str,
                 images_catalog: list, taxonomy: dict,
                 ad_identities: list,
                 graph_ctx: Optional[dict] = None,
                 network_services: Optional[dict] = None,
                 software_inventory: Optional[dict] = None,
                 vulnerabilities: Optional[dict] = None,
                 attack_surface: Optional[dict] = None) -> list:
    """
    For each STIX infrastructure object emit a richly populated host spec.

    New fields (per the cti-unified-base contract):
      - `services[]`        — ATT&CK data-source signal slugs.
      - `domain_membership` — name of an AD identity SDO when correlated.
      - `os` / `ip` / `role` — copied from `x_cti_os` / `x_cti_ip` /
                               `x_cti_role` when set; otherwise fall back
                               to the previous behaviour.
      - `software_required[]` — tool SDOs targeting this host's OS.
    """
    dc_index = _datacomponent_index(taxonomy) if taxonomy else {}

    graph_ctx = graph_ctx or _infra_graph_context(bundle_objects)
    network_services = network_services or {}
    software_inventory = software_inventory or {}
    vulnerabilities = vulnerabilities or {}
    reachable_refs = set(graph_ctx.get("reachable_infrastructure_refs") or [])

    hosts = []
    seen_names = set()
    for o in bundle_objects:
        if o.get("type") != "infrastructure":
            continue

        types = o.get("infrastructure_types") or ["unknown"]
        relationship_edges = _edges_touching(o["id"], graph_ctx)
        if (
            (
                o.get("x_cti_service_category")
                or "hosting-malware" in {str(t).lower() for t in types}
            )
            and not o.get("x_cti_ip")
            and not relationship_edges
            and o.get("id") not in reachable_refs
            and not _looks_like_hostname_token(o.get("name") or "")
        ):
            continue
        # Prefer explicit per-host x_cti_role from stage 2 enrichment.
        role = (o.get("x_cti_role") or "").strip().lower() or _role_from_infra_types(types)

        name_seed = (o.get("name") or "host")
        slug = _slug(name_seed)
        candidate = f"range-{slug}"
        n = 1
        while candidate in seen_names:
            n += 1
            candidate = f"range-{slug}-{n}"
        seen_names.add(candidate)

        # Per-host platform: prefer x_cti_os from stage 2; fall back to
        # the bundle's primary aggregate.
        host_os = (o.get("x_cti_os") or "").strip().lower() or None
        platform = host_os or (primary_platform or "unknown")

        image_candidates = _image_candidates_for_platform(platform, images_catalog)

        # services: concrete host-local services only. ATT&CK
        # data-source/data-component names are telemetry signals at the
        # topology level; they become deployable host services only when
        # a technique is directly related to this infrastructure SDO.
        # Do not fall back to the bundle-wide technique set or every host
        # inherits generic artifacts like Process, Kernel, File, etc.
        host_tids = _co_techniques_for_infrastructure(o["id"], bundle_objects)
        services = set()
        for tid in host_tids:
            signals = dc_index.get(tid)
            if not signals:
                continue
            for tok in _service_tokens_from_signals(signals):
                services.add(tok)
        if o.get("x_cti_service_category") and role and role != "unknown":
            services.add(role)

        # domain_membership: if AD identities exist AND host's role is a
        # member-eligible STIX vocab term (workstation, server-y types),
        # attach the first AD identity name. Membership-eligibility comes
        # from the STIX vocab itself: anything in the vocab that is NOT a
        # router/firewall/network-device infrastructure type is a
        # potential AD member. We avoid hardcoding by checking the
        # negative ("network-device" / "firewall" / "routers-switches"
        # are explicit non-members in the STIX vocab).
        domain_membership = None
        if ad_identities:
            non_member_terms = {"routers-switches", "firewall", "network-device"}
            host_infra_terms = {str(t).lower() for t in types}
            if not (host_infra_terms & non_member_terms):
                # Pick the highest-confidence AD identity.
                ad = max(
                    ad_identities,
                    key=lambda i: float(i.get("x_cti_confidence") or 0.0),
                )
                domain_membership = ad.get("name")

        # software_required: tool SDOs that target this OS.
        software_required = _tools_for_platform(bundle_objects, platform)
        for sw in software_inventory.get(o["id"], []):
            key = (
                (sw.get("cpe") or "").lower(),
                (sw.get("name") or "").lower(),
                (sw.get("version") or "").lower(),
            )
            existing_keys = {
                (
                    (rec.get("cpe") or "").lower(),
                    (rec.get("name") or "").lower(),
                    (rec.get("version") or "").lower(),
                )
                for rec in software_required if isinstance(rec, dict)
            }
            if key not in existing_keys:
                software_required.append(sw)

        vuln_records = vulnerabilities.get(o["id"], [])
        for vuln in vuln_records:
            for hint in vuln.get("software_hints") or []:
                hint_rec = dict(hint)
                hint_rec["source"] = f"NVD CPE applicability for {vuln.get('cve')}"
                hint_rec["cve_refs"] = [vuln.get("cve")]
                key = (
                    (hint_rec.get("cpe") or "").lower(),
                    (hint_rec.get("name") or "").lower(),
                    (hint_rec.get("version") or "").lower(),
                )
                existing_keys = {
                    (
                        (rec.get("cpe") or "").lower(),
                        (rec.get("name") or "").lower(),
                        (rec.get("version") or "").lower(),
                    )
                    for rec in software_required if isinstance(rec, dict)
                }
                if key not in existing_keys:
                    software_required.append(hint_rec)

        network_service_records = network_services.get(o["id"], [])
        for rec in network_service_records:
            service = rec.get("service")
            if service:
                services.add(service)

        host = {
            "name": candidate,
            "stix_id": o.get("id"),
            "role": role,
            "platform": platform,
            "infrastructure_types": list(types),
            "kill_chain_phases": list(o.get("kill_chain_phases") or []),
            "image_candidates": image_candidates,
            "services": sorted(services),
            "network_services": network_service_records,
            "software_required": software_required,
            "vulnerabilities": vuln_records,
            "member_of": [],
            "relationship_edges": relationship_edges,
            "reachable_from_roots": o.get("id") in reachable_refs,
            "inferred_from": [
                f"infrastructure.infrastructure_types={types}",
                f"primary_platform aggregate ({platform})",
            ],
        }
        if graph_ctx.get("root_refs"):
            host["root_refs"] = list(graph_ctx.get("root_refs") or [])

        # Carry through stage 2 enrichment fields verbatim so consumers
        # can see provenance.
        for opt_key, src_key in (("os", "x_cti_os"),
                                  ("ip", "x_cti_ip")):
            if o.get(src_key):
                host[opt_key] = o[src_key]
        if domain_membership:
            host["domain_membership"] = domain_membership
            host["inferred_from"].append(
                f"located-at -> identity({domain_membership})"
            )
        if services:
            host["inferred_from"].append(
                f"ATT&CK data-source signals: {sorted(services)}"
            )
        if network_service_records:
            host["inferred_from"].append(
                "network-traffic SCO services: "
                + ", ".join(
                    f"{r.get('iana_name')}/{r.get('protocol')}:{r.get('port')}"
                    for r in network_service_records
                )
            )
        if software_inventory.get(o["id"]):
            host["inferred_from"].append(
                "software inventory linked to infrastructure SCO/SDO"
            )
        if vuln_records:
            host["inferred_from"].append(
                "vulnerability SDO / NVD CPE applicability linked to infrastructure"
            )
        if attack_surface and attack_surface.get("techniques"):
            host["attack_surface_source"] = attack_surface.get("source")

        hosts.append(host)
    return hosts


# ----------------------------------------------------------------------
# User-account surfacing
# ----------------------------------------------------------------------

def _ansible_user_input(sco: dict, domain_name: Optional[str]) -> dict:
    """
    Build the var shape the range plugin's roles/users role consumes
    (per plugins/range/automation/roles/users/tasks/{domain,local}_users.yml):

        { username, password, is_admin, user_tags }

    `password` is emitted ONLY when the SCO carries a `credential` (stage
    2 redacts by default; `keep_credential=True` preserves it).
    `is_admin` derives from `x_cti_privilege` against the YAML-driven
    privilege vocab (admin / local-admin / sudo / sql-admin all imply
    elevated privileges; the YAML is the source of truth — see
    `app/utilities/data/privilege_keywords.yml`).
    """
    username = (sco.get("user_id") or sco.get("display_name") or "").strip()
    privilege = (sco.get("x_cti_privilege") or "").strip().lower()

    # Privilege -> is_admin via the YAML-driven account_type mapping. We
    # consider any privilege whose mapped STIX account_type ends in
    # "-admin", "-domain" with non-standard privilege, or starts with
    # "sudo"/"sql" to be elevated. The check is structural over the YAML
    # data, NOT a hardcoded set of strings here.
    elevated = _is_elevated_privilege(privilege)

    out = {
        "username": username,
        "is_admin": elevated,
    }
    cred = sco.get("credential")
    if cred:
        out["password"] = cred
    user_tags = sco.get("x_cti_user_tags") or sco.get("x_user_tags")
    if isinstance(user_tags, list) and user_tags:
        out["user_tags"] = list(user_tags)
    return out


@lru_cache(maxsize=1)
def _privilege_vocab() -> dict:
    """
    Load `privilege_keywords.yml` for the privilege -> account_type map.
    The YAML is data, not code — a non-developer can update which
    privilege labels imply elevated rights without touching this file.
    """
    path = Path(__file__).resolve().parent / "data" / "privilege_keywords.yml"
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return doc.get("privilege_to_account_type") or {}
    except Exception:
        return {}


def _is_elevated_privilege(privilege: str) -> bool:
    """
    True iff the privilege label maps to an elevated STIX account type
    per the YAML privilege vocab. "standard"/"unknown" are non-elevated;
    everything else (admin, local-admin, sudo, sql-admin) is elevated.
    The lookup is over YAML data, so the truth set updates by editing
    the YAML, not by patching this file.
    """
    if not privilege:
        return False
    vocab = _privilege_vocab()
    # Anything in the YAML map that ISN'T the explicit non-elevated
    # entries ("standard", "unknown") is treated as elevated.
    non_elevated = {"standard", "unknown"}
    return privilege.lower() in vocab and privilege.lower() not in non_elevated


def derive_user_accounts(bundle_objects: list, identity_index: dict,
                         targeted_identity_refs: Optional[set] = None) -> list:
    """
    Surface every user-account SCO from the bundle as a topology entry.

    For each SCO we attempt to resolve its AD domain via:
      1. A `located-at` relationship pointing to an identity SDO.
      2. Failing that, the SCO's own `x_cti_domain` field.
    """
    targeted_identity_refs = targeted_identity_refs or set()
    out = []
    for o in bundle_objects:
        if o.get("type") != "user-account":
            continue

        username = (o.get("user_id") or o.get("display_name") or "").strip()
        if not username:
            continue

        # Domain resolution.
        domain_ident = _domain_from_located_at(o["id"], bundle_objects, identity_index)
        targeted_identity = False
        if domain_ident:
            domain_name = domain_ident.get("name")
            targeted_identity = domain_ident.get("id") in targeted_identity_refs
        else:
            domain_name = (o.get("x_cti_domain") or "").strip() or None

        ansible_input = _ansible_user_input(o, domain_name)
        if targeted_identity and domain_name:
            tags = ansible_input.setdefault("user_tags", [])
            if domain_name not in tags:
                tags.append(domain_name)

        entry = {
            "username": username,
            "account_type": (o.get("account_type") or "").strip().lower() or None,
            "privilege": (o.get("x_cti_privilege") or "").strip().lower() or None,
            "domain": domain_name,
            "hosting_realm": domain_name or "local",
            "targeted_identity": targeted_identity,
            "organization_unit": domain_name if targeted_identity else None,
            "ansible_role_input": ansible_input,
            "stix_id": o.get("id"),
        }
        out.append(entry)
    return out


# ----------------------------------------------------------------------
# Identities + networks
# ----------------------------------------------------------------------

def derive_identities(bundle_objects: list,
                      targeted_identity_refs: Optional[set] = None) -> list:
    """Mirror every STIX identity SDO at the top of the topology SDO."""
    targeted_identity_refs = targeted_identity_refs or set()
    out = []
    for o in bundle_objects:
        if o.get("type") != "identity":
            continue
        out.append({
            "id": o.get("id"),
            "name": o.get("name"),
            "identity_class": (o.get("identity_class") or "").lower() or None,
            "domain_type": (o.get("x_cti_domain_type") or "").lower() or None,
            "signals": list(o.get("x_cti_signals") or []),
            "confidence": o.get("x_cti_confidence"),
            "targeted": o.get("id") in targeted_identity_refs,
        })
    return out


def _targeted_identity_refs(bundle_objects: list, graph_ctx: dict) -> set:
    """Identity SDOs targeted by campaign/intrusion-set/threat-actor roots."""
    by_id = _objects_by_id(bundle_objects)
    roots = set(graph_ctx.get("root_refs") or [])
    out = set()
    for e in _relationship_edges(bundle_objects, None):
        if e.get("relationship_type") != "targets":
            continue
        src = e.get("source_ref")
        tgt = e.get("target_ref")
        if src in roots and by_id.get(tgt, {}).get("type") == "identity":
            out.add(tgt)
        if tgt in roots and by_id.get(src, {}).get("type") == "identity":
            out.add(src)
    return out


def derive_networks(bundle_objects: list, hosts: list) -> list:
    """
    Group infrastructure SDOs into networks by their `located-at`
    relationship to an identity SDO. Hosts that don't share a target
    identity get a singleton network.
    """
    # Map host slug back to its underlying infrastructure-SDO id.
    inf_id_by_slug = {}
    for o in bundle_objects:
        if o.get("type") != "infrastructure":
            continue
        slug = f"range-{_slug(o.get('name') or 'host')}"
        # If duplicates exist they're disambiguated with -2/-3 — but we
        # only need the FIRST mapping; networks group by identity, not
        # by hostname, so the disambiguation suffix doesn't change the
        # set.
        inf_id_by_slug.setdefault(slug, o["id"])

    # For each host, find its located-at identity (if any).
    groups = {}
    orphans = []
    for h in hosts:
        inf_id = inf_id_by_slug.get(h["name"]) or inf_id_by_slug.get(
            re.sub(r"-\d+$", "", h["name"])
        )
        if not inf_id:
            orphans.append(h["name"])
            continue
        anchor = None
        for r in bundle_objects:
            if r.get("type") != "relationship":
                continue
            if r.get("relationship_type") != "located-at":
                continue
            if r.get("source_ref") != inf_id:
                continue
            tgt = r.get("target_ref") or ""
            if tgt.startswith("identity--"):
                anchor = tgt
                break
        if anchor:
            groups.setdefault(anchor, []).append(h["name"])
        else:
            orphans.append(h["name"])

    networks = []
    name_by_id = {o.get("id"): o.get("name") for o in bundle_objects
                  if o.get("type") == "identity"}
    for ident_id, members in groups.items():
        anchor_name = name_by_id.get(ident_id) or "unnamed"
        networks.append({
            "name": _slug(anchor_name) + "-net",
            "members": sorted(members),
            "anchor_identity": ident_id,
        })
    if orphans:
        networks.append({
            "name": "unanchored-net",
            "members": sorted(orphans),
            "anchor_identity": None,
        })
    return networks


def derive_observable_surfaces(bundle_objects: list) -> dict:
    """Carry first-class STIX observable surfaces into topology metadata."""
    networks = []
    file_paths = []
    registry_keys = []
    seen = {"networks": set(), "file_paths": set(), "registry_keys": set()}

    for o in bundle_objects:
        if not isinstance(o, dict):
            continue
        otype = o.get("type")
        if otype == "ipv4-addr":
            value = (o.get("value") or "").strip()
            if value and "/" in value and value not in seen["networks"]:
                networks.append({"cidr": value, "stix_id": o.get("id")})
                seen["networks"].add(value)
        elif otype == "file":
            value = (o.get("x_path") or o.get("name") or "").strip()
            key = value.lower()
            if value and key not in seen["file_paths"]:
                file_paths.append(value)
                seen["file_paths"].add(key)
        elif otype == "windows-registry-key":
            value = (o.get("key") or "").strip()
            key = value.lower()
            if value and key not in seen["registry_keys"]:
                registry_keys.append(value)
                seen["registry_keys"].add(key)

    return {
        "networks": networks,
        "file_paths": file_paths,
        "registry_keys": registry_keys,
    }


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def build_range_topology(bundle: dict, taxonomy: dict,
                         images_catalog: list = None) -> dict:
    """
    Construct the x-cti-range-topology SDO from a stage-2 STIX bundle.

    Args:
        bundle: STIX 2.1 bundle dict with 'objects' list.
        taxonomy: ATT&CK taxonomy from cti_taxonomy_loader.load_mitre_taxonomy.
            Optionally carries a `_raw_objects` list of every ATT&CK SDO —
            required to walk the detection-strategy / data-component graph
            for service inference. Falls back to lazy-loading the full
            ATT&CK bundle if absent.
        images_catalog: parsed list from plugins/range/conf/onprem_images.yml
            (the value of the top-level 'images' key). If None,
            image_candidates comes back empty.

    Returns:
        A single SDO dict ready to be appended to a STIX bundle.
    """
    objects = bundle.get("objects", []) if isinstance(bundle, dict) else []

    plat = aggregate_target_platforms(objects, taxonomy)
    ad_idents = _ad_identities(objects)
    identity_index = {o["id"]: o for o in objects if o.get("type") == "identity"}
    graph_ctx = _infra_graph_context(objects)
    network_services, network_edges = _network_services_by_infrastructure(objects)
    software_inventory = _software_inventory_by_infrastructure(objects)
    vulnerabilities = _vulnerabilities_by_infrastructure(objects)
    attack_surface = _attack_surface_from_techniques(objects, taxonomy)
    targeted_idents = _targeted_identity_refs(objects, graph_ctx)

    hosts = derive_hosts(
        objects, plat["primary"], images_catalog or [], taxonomy, ad_idents,
        graph_ctx=graph_ctx,
        network_services=network_services,
        software_inventory=software_inventory,
        vulnerabilities=vulnerabilities,
        attack_surface=attack_surface,
    )

    required_infrastructure_missing: list[dict] = []
    ad_tids = _ad_implicating_technique_ids(objects, taxonomy)
    if len(ad_tids) >= 2 and not _has_dc_infrastructure(objects, hosts):
        ad_services = _ad_services_from_techniques(objects, taxonomy, ad_tids)
        domain_hint = None
        if ad_idents:
            ad = max(ad_idents,
                     key=lambda i: float(i.get("x_cti_confidence") or 0.0))
            domain_hint = (ad.get("name") or "").strip() or None
        required_infrastructure_missing.append({
            "role": "dc",
            "platform": "windows",
            "services": list(ad_services) if ad_services else [
                "active-directory-domain-services", "kerberos", "dns",
            ],
            "domain": domain_hint,
            "techniques": sorted(ad_tids),
            "reason": (
                "ATT&CK techniques and Active Directory telemetry imply a "
                "domain controller, but no STIX infrastructure SDO or AE "
                "plan host declares one"
            ),
        })

    user_accounts = derive_user_accounts(objects, identity_index, targeted_idents)
    identities = derive_identities(objects, targeted_idents)
    networks = derive_networks(objects, hosts)
    observable_surfaces = derive_observable_surfaces(objects)
    if observable_surfaces["networks"]:
        existing_cidrs = {
            n.get("cidr") for n in networks
            if isinstance(n, dict) and n.get("cidr")
        }
        for net in observable_surfaces["networks"]:
            if net.get("cidr") not in existing_cidrs:
                networks.append({
                    "name": _slug(net["cidr"]) + "-net",
                    "cidr": net["cidr"],
                    "members": [],
                    "anchor_identity": None,
                    "stix_id": net.get("stix_id"),
                })
                existing_cidrs.add(net.get("cidr"))

    return {
        "type": "x-cti-range-topology",
        "spec_version": "2.1",
        "id": new_id(),
        "created": now(),
        "modified": now(),
        "primary_platform": plat["primary"],
        "primary_platform_confidence": plat["primary_confidence"],
        "primary_platform_source": plat["provenance"],
        "platform_tally": plat["tally"],
        "derived_from": plat["derived_from"],
        "hosts": hosts,
        "user_accounts": user_accounts,
        "identities": identities,
        "networks": networks,
        "network_edges": network_edges,
        "infrastructure_graph": {
            "root_refs": graph_ctx.get("root_refs") or [],
            "allowed_relationship_types": graph_ctx.get("allowed_relationship_types") or [],
            "reachable_infrastructure_refs": graph_ctx.get("reachable_infrastructure_refs") or [],
            "edges": graph_ctx.get("edges") or [],
        },
        "attack_surface": attack_surface,
        "required_infrastructure_missing": required_infrastructure_missing,
        "file_paths": observable_surfaces["file_paths"],
        "registry_keys": observable_surfaces["registry_keys"],
        "targeted_identity_refs": sorted(targeted_idents),
    }
