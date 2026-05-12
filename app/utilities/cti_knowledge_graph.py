"""Persistent CTI topology knowledge graph.

Stores cumulative CTI extraction results in SQLite so repeated ingests can
diff/merge by canonical identifiers without adding a graph database service.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional


_THIS_DIR = Path(__file__).resolve().parent
_MCP_DATA_DIR = _THIS_DIR.parents[1] / "data"
_DEFAULT_DB = _MCP_DATA_DIR / "cti_knowledge_graph.sqlite"


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def default_db_path() -> Path:
    return _DEFAULT_DB


def _norm(text: str) -> str:
    if not text:
        return ""
    import re
    return re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _external_id(obj: dict, source_name: str) -> Optional[str]:
    wanted = source_name.lower()
    for er in obj.get("external_references") or []:
        if (er.get("source_name") or "").lower() == wanted:
            eid = (er.get("external_id") or "").strip()
            if eid:
                return eid
    return None


def canonical_key(obj: dict) -> str:
    """Stable, privacy-preserving key for a STIX/topology node."""
    otype = obj.get("type") or obj.get("node_type") or "object"
    if otype == "attack-pattern":
        tid = _external_id(obj, "mitre-attack")
        if tid:
            return f"attack:{tid.upper()}"
    if otype == "vulnerability":
        cve = _external_id(obj, "cve") or obj.get("name")
        if cve:
            return f"cve:{str(cve).upper()}"
    if otype == "software":
        cpe = obj.get("cpe")
        if cpe:
            return f"cpe:{cpe}"
        name = _norm(obj.get("name") or "")
        version = _norm(obj.get("version") or "")
        vendor = _norm(obj.get("vendor") or "")
        return f"software:{vendor}:{name}:{version}"
    if otype == "x-cti-range-host":
        ip = obj.get("ip")
        if ip:
            return f"host-ip-sha256:{_hash_token(ip)}"
        name = obj.get("name")
        if name:
            return f"host:{_hash_token(name.lower())}"
    if otype == "infrastructure":
        ip = obj.get("x_cti_ip")
        if ip:
            return f"infra-ip-sha256:{_hash_token(ip)}"
    name = obj.get("name") or obj.get("id") or json.dumps(obj, sort_keys=True)
    return f"{otype}:{_norm(name) or _hash_token(str(name))}"


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path or _DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            canonical_key TEXT PRIMARY KEY,
            stix_id TEXT,
            type TEXT,
            name TEXT,
            first_seen TEXT,
            last_seen TEXT,
            json TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            source_key TEXT,
            target_key TEXT,
            relationship_type TEXT,
            first_seen TEXT,
            last_seen TEXT,
            count INTEGER DEFAULT 1,
            json TEXT,
            PRIMARY KEY (source_key, target_key, relationship_type)
        )
    """)
    return conn


def _upsert_node(conn: sqlite3.Connection, obj: dict) -> str:
    key = canonical_key(obj)
    now = _now()
    conn.execute(
        """
        INSERT INTO nodes(canonical_key, stix_id, type, name, first_seen, last_seen, json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(canonical_key) DO UPDATE SET
            stix_id=excluded.stix_id,
            type=excluded.type,
            name=excluded.name,
            last_seen=excluded.last_seen,
            json=excluded.json
        """,
        (
            key,
            obj.get("id") or obj.get("stix_id"),
            obj.get("type") or obj.get("node_type"),
            obj.get("name"),
            now,
            now,
            json.dumps(obj, sort_keys=True, default=str),
        ),
    )
    return key


def _upsert_edge(conn: sqlite3.Connection, source_key: str, target_key: str,
                 relationship_type: str, payload: dict) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO edges(source_key, target_key, relationship_type, first_seen, last_seen, count, json)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(source_key, target_key, relationship_type) DO UPDATE SET
            last_seen=excluded.last_seen,
            count=count + 1,
            json=excluded.json
        """,
        (
            source_key,
            target_key,
            relationship_type,
            now,
            now,
            json.dumps(payload, sort_keys=True, default=str),
        ),
    )


def persist_bundle_topology(bundle: dict, topology: dict,
                            db_path: Optional[Path] = None) -> dict:
    """Persist STIX objects, topology hosts, and relationship edges."""
    objects = bundle.get("objects") or []
    by_id = {
        o.get("id"): o for o in objects
        if isinstance(o, dict) and o.get("id")
    }
    conn = _connect(db_path)
    nodes = 0
    edges = 0
    try:
        for obj in objects:
            if not isinstance(obj, dict) or not obj.get("id"):
                continue
            _upsert_node(conn, obj)
            nodes += 1

        for host in topology.get("hosts") or []:
            if not isinstance(host, dict):
                continue
            host_obj = {
                "type": "x-cti-range-host",
                "id": host.get("name"),
                "name": host.get("name"),
                "ip": host.get("ip"),
                "role": host.get("role"),
                "platform": host.get("platform"),
                "stix_id": host.get("stix_id"),
            }
            host_key = _upsert_node(conn, host_obj)
            nodes += 1
            stix_id = host.get("stix_id")
            if stix_id and stix_id in by_id:
                inf_key = canonical_key(by_id[stix_id])
                _upsert_edge(conn, inf_key, host_key, "materializes-as", host)
                edges += 1

        for rel in objects:
            if not isinstance(rel, dict) or rel.get("type") != "relationship":
                continue
            src = by_id.get(rel.get("source_ref"))
            tgt = by_id.get(rel.get("target_ref"))
            if not (src and tgt):
                continue
            _upsert_edge(
                conn,
                canonical_key(src),
                canonical_key(tgt),
                rel.get("relationship_type") or "related-to",
                rel,
            )
            edges += 1

        for edge in topology.get("network_edges") or []:
            for host_ref in edge.get("host_refs") or []:
                host = next(
                    (h for h in topology.get("hosts") or []
                     if h.get("stix_id") == host_ref),
                    None,
                )
                if not host:
                    continue
                host_key = canonical_key({
                    "type": "x-cti-range-host",
                    "name": host.get("name"),
                    "ip": host.get("ip"),
                })
                svc_key = canonical_key({
                    "type": "service",
                    "name": f"{edge.get('service')}:{edge.get('protocol')}:{edge.get('port')}",
                })
                _upsert_node(conn, {
                    "type": "service",
                    "name": f"{edge.get('service')}:{edge.get('protocol')}:{edge.get('port')}",
                })
                _upsert_edge(conn, host_key, svc_key, "exposes-service", edge)
                nodes += 1
                edges += 1

        conn.commit()
    finally:
        conn.close()
    return {
        "db_path": str(Path(db_path or _DEFAULT_DB)),
        "nodes_seen": nodes,
        "edges_seen": edges,
    }
