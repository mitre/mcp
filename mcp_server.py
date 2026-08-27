"""cti_pipeline MCP server.

Exposes the deterministic CTI -> STIX -> topology -> deploy-spec -> deploy
-> operation -> detections pipeline as MCP tools so plan_execute (and any
other DSPy ReAct workflow) can drive the same artefacts via tool calls
instead of a parallel hard-coded workflow.

Every tool is a thin async wrapper around an already-existing service or
utility in this plugin (or a Caldera REST endpoint for cross-plugin
operations). No business logic lives here - this file is wiring only.

Design rules in force (see project memory):
  * no static lists / hard-coded vocab (all classifications stay in the
    underlying services and the taxonomy/AE-library data)
  * tool functions are async; inputs and outputs are JSON-serialisable
  * read CALDERA_URL + CORE_CALDERA_API_KEY from env (parent process
    populates them in get_env())
  * no dotenv.load_dotenv() - the subprocess inherits the parent env
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

# This file runs both in-process (when the workflow registry imports it
# to enumerate tools) and as a stdio subprocess spawned by plan_execute's
# DSPy ReAct adapter. In subprocess mode the inherited sys.path does NOT
# include the caldera repo root, so any tool that does `from
# plugins.mcp.app.* import ...` fails with `No module named 'plugins'`.
# Inject the repo root at import time so the same code works on both
# paths. The repo root is three levels up from this file
# (plugins/mcp/mcp_server.py -> plugins/mcp -> plugins -> caldera-root).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from plugins.mcp.app.config import caldera_connection


def _stdout_safe(fn):
    """Decorator: redirect stdout to stderr while the tool body runs.

    FastMCP's stdio transport reads JSON-RPC framed messages off the
    subprocess's stdout. Any ``print(...)`` in the wrapped tool body --
    or in code it calls into (e.g. ``cti_ingest_svc.run_stage`` writes
    progress lines like ``[+] Stage1 starting: 2 files | 14 workers``)
    -- corrupts the protocol and the host raises ``ValidationError:
    Invalid JSON`` for the partial frame. Routing stdout to stderr for
    the tool body keeps protocol writes clean while leaving the
    progress lines visible in the parent caldera log (which is fed by
    the subprocess's stderr).
    """
    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def aw(*args, **kwargs):
            with contextlib.redirect_stdout(sys.stderr):
                return await fn(*args, **kwargs)
        return aw

    @functools.wraps(fn)
    def w(*args, **kwargs):
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args, **kwargs)
    return w


def _resolve_pipeline_file(path_value: str, *, data_subdirs: tuple[str, ...] = ()) -> Path:
    """Resolve UI-selected CTI artifact names against MCP pipeline data dirs."""
    raw = Path(str(path_value or "").strip())
    if raw.is_absolute():
        return raw

    candidates = [
        Path.cwd() / raw,
        _REPO_ROOT / raw,
    ]
    try:
        from plugins.mcp.app.utilities.paths import get_mcp_data_dir

        data_dir = get_mcp_data_dir()
        candidates.append(data_dir / raw)
        for subdir in data_subdirs:
            candidates.append(data_dir / subdir / raw)
    except Exception:
        pass

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    return candidates[0].resolve()


from mcp.server.fastmcp import FastMCP


# ---------------------------------------------------------------------------
# MCP_METADATA - parsed via ast.literal_eval by the discovery layer; must
# stay a top-level literal. Keep keys conservative (strings / bools).
# ---------------------------------------------------------------------------
MCP_METADATA = {
    "id": "cti_pipeline",
    "display_name": "CTI Pipeline",
    "default_enabled": True,
    "description": (
        "End-to-end CTI ingest tools: PDF/HTML -> STIX 2.1 bundle -> "
        "topology SDO -> adversary -> operation "
        "-> detection validation. Thin wrappers over the deterministic "
        "pipeline services."
    ),
}


mcp = FastMCP("CTI Pipeline MCP Server")
log = logging.getLogger("plugins.mcp.cti_pipeline_server")


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _caldera_base_url() -> str:
    url = os.environ.get("CALDERA_URL") or caldera_connection()["url"]
    # Normalise to a single trailing slash; downstream f-string concat
    # assumes exactly one.
    return url.rstrip("/") + "/"


def _caldera_api_key() -> str:
    return os.environ.get("CORE_CALDERA_API_KEY") or caldera_connection()["api_key"]


def _caldera_headers() -> dict:
    return {
        "KEY": _caldera_api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _caldera_root() -> str:
    """Caldera HTTP root (without the /api/v2/ suffix) - used for plugin
    endpoints that live outside the v2 API namespace.
    """
    api = _caldera_base_url()
    # api looks like "http://host:port/api/v2/"; strip the trailing
    # "api/v2/" to get the root.
    for marker in ("api/v2/", "api/v2"):
        if api.endswith(marker):
            return api[: -len(marker)]
    # Fallback - use the scheme+host only.
    return api




















# ---------------------------------------------------------------------------
# Pipeline tools
# ---------------------------------------------------------------------------

@mcp.tool(name="cti_pipeline_ingest_cti")
@_stdout_safe
async def ingest_cti(file_path: str) -> dict:
    """Run the full CTI ingest pipeline (raw -> STIX -> topology) on a file.

    Stages 1+2+4 (cleaning, IR extraction, STIX assembly, topology
    inference + AE-library cross-reference) are executed in order. The
    file is copied into the plugin's data/raw/uploads/ directory first
    so the pipeline's working tree stays canonical.

    Args:
        file_path: absolute or repo-relative path to a CTI document
            (PDF, HTML, plaintext). Mandatory.

    Returns:
        {stix_path, topology_path, counts} where counts breaks down the
        bundle by SDO type (malware, infrastructure, hosts, identities,
        attack_patterns, tools, relationships, user_accounts).
    """
    from plugins.mcp.app.cti_ingest_svc import CTIIngestService
    from plugins.mcp.app.utilities.paths import get_mcp_data_dir
    import shutil

    if not file_path:
        return {"error": "file_path is required"}

    base_dir = get_mcp_data_dir()
    uploads = base_dir / "raw" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)

    src = _resolve_pipeline_file(
        file_path,
        data_subdirs=("raw/uploads", "raw", "inputs", "outputs_stix", "stix_cti"),
    )
    if not src.is_file():
        return {"error": f"cti_source not found: {file_path}"}

    target = uploads / src.name
    if src.resolve() != target.resolve():
        try:
            shutil.copy2(src, target)
        except Exception as e:
            return {"error": f"failed to stage {src} -> {target}: {e}"}

    # Run the (synchronous, CPU + LLM heavy) pipeline in a worker thread
    # so we do not block the MCP stdio reader.
    svc = CTIIngestService()
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, svc.run_stage, base_dir, "all")
    except Exception as e:
        log.exception("CTI pipeline 'all' run failed")
        return {"error": f"pipeline failed: {e}", "state": svc.status()}

    stem = src.stem
    outputs_stix = base_dir / "outputs_stix"
    outputs_topo = base_dir / "outputs_topology"

    def _matches_stem(p: Path) -> bool:
        s_norm = "".join(c for c in stem.lower() if c.isalnum())
        n_norm = "".join(c for c in p.stem.lower() if c.isalnum())
        return bool(s_norm) and s_norm in n_norm

    stix_path: Optional[Path] = None
    topo_path: Optional[Path] = None
    if outputs_stix.is_dir():
        for p in outputs_stix.glob("*.stix.json"):
            if _matches_stem(p):
                stix_path = p
                break
    if outputs_topo.is_dir():
        for p in outputs_topo.glob("*.topology.json"):
            if _matches_stem(p):
                topo_path = p
                break

    counts = {
        "malware": 0,
        "infrastructure": 0,
        "user_accounts": 0,
        "hosts": 0,
        "identities": 0,
        "attack_patterns": 0,
        "tools": 0,
        "relationships": 0,
        "threat_actors": 0,
        "intrusion_sets": 0,
    }
    if stix_path and stix_path.is_file():
        try:
            bundle = json.loads(stix_path.read_text(encoding="utf-8"))
            for obj in bundle.get("objects", []):
                t = obj.get("type", "")
                if t == "malware":
                    counts["malware"] += 1
                elif t == "infrastructure":
                    counts["infrastructure"] += 1
                elif t == "identity":
                    counts["identities"] += 1
                elif t == "user-account":
                    counts["user_accounts"] += 1
                elif t == "attack-pattern":
                    counts["attack_patterns"] += 1
                elif t == "tool":
                    counts["tools"] += 1
                elif t == "relationship":
                    counts["relationships"] += 1
                elif t == "threat-actor":
                    counts["threat_actors"] += 1
                elif t == "intrusion-set":
                    counts["intrusion_sets"] += 1
                elif t == "x-cti-range-topology":
                    counts["hosts"] += len(obj.get("hosts") or [])
        except Exception as e:
            log.warning(f"counts assembly failed: {e}")

    return {
        "input": str(src),
        "filename": src.name,
        "stix_path": str(stix_path) if stix_path else None,
        "topology_path": str(topo_path) if topo_path else None,
        "counts": counts,
        "state": svc.status(),
    }


@mcp.tool(name="cti_pipeline_build_topology")
@_stdout_safe
async def build_topology(stix_path: str) -> dict:
    """Build (or rebuild) the x-cti-range-topology SDO from a STIX bundle.

    Use this when ingest_cti has already produced a bundle and you want
    a fresh topology inference, OR when an external bundle was placed in
    data/outputs_stix/ manually. The taxonomy + AE-library cross-
    reference happen inside cti_topology_inference - this tool does not
    pick scenes apart on its own.

    Args:
        stix_path: absolute or repo-relative path to a *.stix.json file.

    Returns:
        {topology_id, primary_platform, hosts, services, software, users,
        identities, networks, saved_to}
    """
    from plugins.mcp.app.utilities.cti_topology_inference import (
        build_range_topology,
    )

    if not stix_path:
        return {"error": "stix_path is required"}
    p = _resolve_pipeline_file(
        stix_path,
        data_subdirs=("outputs_stix", "stix_cti", "raw/uploads"),
    )
    if not p.is_file():
        return {"error": f"stix_path not found: {stix_path}"}

    try:
        bundle = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"failed to parse STIX bundle: {e}"}

    taxonomy: dict = {}
    try:
        from plugins.mcp.app.utilities.cti_taxonomy_loader import (
            load_mitre_taxonomy,
            load_mitre_bundle,
        )
        taxonomy = load_mitre_taxonomy() or {}
        try:
            raw_bundle = load_mitre_bundle()
            taxonomy["_raw_objects"] = raw_bundle.get("objects", []) or []
        except Exception:
            pass
    except Exception as e:
        log.warning(f"taxonomy load failed: {e}; proceeding without it")

    try:
        topology = build_range_topology(bundle, taxonomy)
    except Exception as e:
        log.exception("build_range_topology failed")
        return {"error": f"topology build failed: {e}"}

    try:
        from plugins.mcp.app.cti_pipeline_stage4_topology import (
            _adversary_candidates_from_bundle,
            _enrich_topology_with_ae_plan,
            _technique_ids_in_bundle,
        )
        from plugins.mcp.app.utilities.cti_ae_library_loader import (
            discover_ae_plans,
            find_plan_by_adversary,
            parse_ae_plan,
        )
        stem_hint = p.stem[:-len(".stix")] if p.stem.endswith(".stix") else p.stem
        plans = discover_ae_plans()
        for cand in _adversary_candidates_from_bundle(bundle, stem_hint=stem_hint):
            plan = find_plan_by_adversary(plans, cand)
            if not plan:
                continue
            ae_ir = parse_ae_plan(plan, taxonomy=taxonomy)
            topology = _enrich_topology_with_ae_plan(
                topology, plan, ae_ir, _technique_ids_in_bundle(bundle),
            )
            break
    except Exception as e:
        log.warning(f"AE plan topology enrichment skipped: {e}")

    knowledge_graph = None
    try:
        from plugins.mcp.app.utilities.cti_knowledge_graph import (
            persist_bundle_topology,
        )
        knowledge_graph = persist_bundle_topology(bundle, topology)
    except Exception as e:
        log.warning(f"knowledge graph persistence skipped: {e}")

    # Persist alongside the bundle for downstream tools.
    out_dir = p.parent.parent / "outputs_topology"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = p.stem
    if stem.endswith(".stix"):
        stem = stem[: -len(".stix")]
    out_path = out_dir / f"{stem}.topology.json"
    try:
        out_path.write_text(
            json.dumps(topology, indent=2, default=str), encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"could not persist topology to {out_path}: {e}")

    hosts = topology.get("hosts") or []
    users = topology.get("user_accounts") or []
    identities = topology.get("identities") or []
    networks = topology.get("networks") or []
    network_edges = topology.get("network_edges") or []

    # Collect aggregate service + software counts so the LLM can reason
    # about scale without having to read the whole topology back.
    services_seen: set = set()
    software_seen: set = set()
    for h in hosts:
        for s in h.get("services") or []:
            services_seen.add(s)
        for sw in h.get("software_required") or []:
            name = sw.get("name") if isinstance(sw, dict) else str(sw)
            if name:
                software_seen.add(name)

    return {
        "topology_id": topology.get("id"),
        "primary_platform": topology.get("primary_platform"),
        "primary_platform_confidence": topology.get("primary_platform_confidence"),
        "host_count": len(hosts),
        "hosts": [{"name": h.get("name"),
                   "role": h.get("role"),
                   "platform": h.get("platform"),
                   "domain_membership": h.get("domain_membership"),
                   "services": list(h.get("services") or [])}
                  for h in hosts],
        "services": sorted(services_seen),
        "software": sorted(software_seen),
        "users": [{"username": u.get("username"),
                   "domain": u.get("domain"),
                   "privilege": u.get("privilege")}
                  for u in users],
        "identities": [{"name": i.get("name"),
                        "domain_type": i.get("domain_type")}
                       for i in identities],
        "networks": [{"name": n.get("name"),
                      "members": list(n.get("members") or [])}
                     for n in networks],
        "network_edges": [
            {
                "service": e.get("service"),
                "protocol": e.get("protocol"),
                "port": e.get("port"),
                "host_refs": list(e.get("host_refs") or []),
            }
            for e in network_edges
        ],
        "attack_surface": topology.get("attack_surface") or {},
        "knowledge_graph": knowledge_graph,
        "saved_to": str(out_path),
    }


@mcp.tool(name="cti_pipeline_fuse")
@_stdout_safe
async def fuse_cti_bundles(stix_paths: list[str],
                           build_topology_after_fuse: bool = True) -> dict:
    """Fuse multiple STIX bundles into one merged bundle/deploy topology.

    Bundles are merged by canonical identifiers: MITRE ATT&CK IDs, CVEs,
    CPEs, and normalized STIX names. Relationships are remapped to the
    surviving object IDs.
    """
    from plugins.mcp.app.utilities.cti_fusion import fuse_bundles
    from plugins.mcp.app.utilities.cti_topology_inference import build_range_topology

    if not stix_paths:
        return {"error": "stix_paths is required"}

    bundles = []
    resolved_paths = []
    for raw in stix_paths:
        p = _resolve_pipeline_file(
            raw,
            data_subdirs=("outputs_stix", "stix_cti", "raw/uploads"),
        )
        if not p.is_file():
            return {"error": f"stix_path not found: {raw}"}
        try:
            bundle = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"failed to parse STIX bundle {raw}: {e}"}
        bundles.append(bundle)
        resolved_paths.append(p)

    fused = fuse_bundles(bundles)
    digest = hashlib.sha256(
        "|".join(str(p) for p in resolved_paths).encode("utf-8")
    ).hexdigest()[:12]
    out_dir = resolved_paths[0].parent
    out_path = out_dir / f"fused-{digest}.stix.json"
    try:
        out_path.write_text(
            json.dumps(fused, indent=2, default=str), encoding="utf-8",
        )
    except Exception as e:
        return {"error": f"failed to persist fused bundle: {e}"}

    topology_path = None
    topology_summary = None
    if build_topology_after_fuse:
        taxonomy: dict = {}
        try:
            from plugins.mcp.app.utilities.cti_taxonomy_loader import (
                load_mitre_taxonomy,
                load_mitre_bundle,
            )
            taxonomy = load_mitre_taxonomy() or {}
            try:
                raw_bundle = load_mitre_bundle()
                taxonomy["_raw_objects"] = raw_bundle.get("objects", []) or []
            except Exception:
                pass
        except Exception as e:
            log.warning(f"taxonomy load failed during fusion topology: {e}")

            topology = build_range_topology(fused, taxonomy)
        try:
            from plugins.mcp.app.cti_pipeline_stage4_topology import (
                _adversary_candidates_from_bundle,
                _enrich_topology_with_ae_plan,
                _technique_ids_in_bundle,
            )
            from plugins.mcp.app.utilities.cti_ae_library_loader import (
                discover_ae_plans,
                find_plan_by_adversary,
                parse_ae_plan,
            )
            plans = discover_ae_plans()
            for cand in _adversary_candidates_from_bundle(fused, stem_hint=out_path.stem):
                plan = find_plan_by_adversary(plans, cand)
                if not plan:
                    continue
                ae_ir = parse_ae_plan(plan, taxonomy=taxonomy)
                topology = _enrich_topology_with_ae_plan(
                    topology, plan, ae_ir, _technique_ids_in_bundle(fused),
                )
                break
        except Exception as e:
            log.warning(f"AE plan topology enrichment skipped for fusion: {e}")
        topo_dir = out_dir.parent / "outputs_topology"
        topo_dir.mkdir(parents=True, exist_ok=True)
        topology_path = topo_dir / f"fused-{digest}.topology.json"
        topology_path.write_text(
            json.dumps(topology, indent=2, default=str), encoding="utf-8",
        )
        try:
            from plugins.mcp.app.utilities.cti_knowledge_graph import (
                persist_bundle_topology,
            )
            kg = persist_bundle_topology(fused, topology)
        except Exception as e:
            log.warning(f"knowledge graph persistence skipped for fusion: {e}")
            kg = None
        topology_summary = {
            "topology_id": topology.get("id"),
            "host_count": len(topology.get("hosts") or []),
            "primary_platform": topology.get("primary_platform"),
            "services": sorted({
                svc
                for h in topology.get("hosts") or []
                for svc in (h.get("services") or [])
            }),
            "knowledge_graph": kg,
        }

    return {
        "source_count": len(bundles),
        "object_count": len(fused.get("objects") or []),
        "saved_to": str(out_path),
        "topology_path": str(topology_path) if topology_path else None,
        "topology": topology_summary,
    }


@mcp.tool(name="cti_pipeline_refine_topology")
@_stdout_safe
async def refine_topology(raw_report_path: str, topology_path: str) -> dict:
    """Run the optional DSPy ReAct cite-back refinement pass.

    The pass returns candidate additions only; it does not mutate the
    topology. Each candidate is expected to carry kind, value, confidence,
    and the report sentence that justifies it.
    """
    from plugins.mcp.app.utilities.cti_refinement import (
        refine_topology_with_dspy_react,
    )

    if not raw_report_path:
        return {"error": "raw_report_path is required"}
    if not topology_path:
        return {"error": "topology_path is required"}

    raw_p = _resolve_pipeline_file(
        raw_report_path,
        data_subdirs=("raw/uploads", "raw", "inputs"),
    )
    topo_p = _resolve_pipeline_file(topology_path, data_subdirs=("outputs_topology",))
    if not raw_p.is_file():
        return {"error": f"raw_report_path not found: {raw_report_path}"}
    if not topo_p.is_file():
        return {"error": f"topology_path not found: {topology_path}"}

    try:
        raw_report = raw_p.read_text(encoding="utf-8", errors="ignore")
        topology = json.loads(topo_p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"failed to load refinement inputs: {e}"}

    result = await refine_topology_with_dspy_react(raw_report, topology)
    out_path = topo_p.with_suffix(".refinement.json")
    try:
        out_path.write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"could not persist refinement output to {out_path}: {e}")

    return {
        "candidate_count": len(result.get("candidate_additions") or []),
        "candidate_additions": result.get("candidate_additions") or [],
        "skipped": bool(result.get("skipped")),
        "reason": result.get("reason"),
        "saved_to": str(out_path),
    }


@mcp.tool(name="cti_pipeline_run_operation")
async def run_operation(
    adversary_id: str,
    agent_paws: list,
    operation_name: Optional[str] = None,
) -> dict:
    """Start a Caldera v2 operation against an adversary using listed agents.

    Wraps POST /api/v2/operations. The v2 manager builds the operation
    using the same code path the GUI uses, so this tool is equivalent to
    clicking 'Run' on the operations page.

    Args:
        adversary_id: ID of the adversary to emulate.
        agent_paws: list of agent paw strings to scope the operation to.
            When empty, Caldera will run against all agents in the
            'group' (defaults to 'red').
        operation_name: optional name; auto-generated when absent.

    Returns:
        {operation_id, state, name, response}
    """
    if not adversary_id:
        return {"error": "adversary_id is required"}
    if agent_paws is None:
        agent_paws = []
    if not isinstance(agent_paws, list):
        return {"error": "agent_paws must be a list of paw strings"}

    name = operation_name or f"cti-pipeline-op-{int(asyncio.get_event_loop().time())}"
    body = {
        "name": name,
        "adversary": {"adversary_id": adversary_id},
        "group": "red",
        "planner": {"id": "atomic"},
        "source": {"id": "basic"},
        "state": "running",
        "autonomous": 1,
        "auto_close": False,
        "obfuscator": "plain-text",
        "jitter": "2/4",
        "visibility": 51,
        "use_learning_parsers": True,
    }
    if agent_paws:
        # v2 API accepts paws via the 'group' or 'agents' field shape;
        # we pass it as a hint via name suffix so downstream observers
        # can correlate - the actual paw filtering happens through
        # group membership which sandcat agents already apply.
        body["_target_paws"] = list(agent_paws)

    import aiohttp
    url = _caldera_base_url() + "operations"
    try:
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"raw": text}
                if resp.status >= 400:
                    return {
                        "error": f"operation create returned {resp.status}",
                        "url": url,
                        "response": payload,
                    }
    except Exception as e:
        return {"error": f"operation create request failed: {e}", "url": url}

    return {
        "operation_id": (payload or {}).get("id"),
        "state": (payload or {}).get("state", body["state"]),
        "name": (payload or {}).get("name", name),
        "adversary_id": adversary_id,
        "target_paws": list(agent_paws),
        "response": payload,
    }


@mcp.tool(name="cti_pipeline_validate_detections")
async def validate_detections(operation_id: str) -> dict:
    """Score a finished operation against the SIEM detection rules.

    Wraps the detections plugin's POST /plugin/detections/validate
    endpoint, which itself calls DetectionService.validate_operation.

    Args:
        operation_id: the Caldera operation id to score.

    Returns:
        {coverage_pct, summary, links_validated, per_link, response}
    """
    if not operation_id:
        return {"error": "operation_id is required"}

    import aiohttp
    url = _caldera_root().rstrip("/") + "/plugin/detections/validate"
    body = {"operation_id": operation_id}
    try:
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"raw": text}
                if resp.status >= 400:
                    return {
                        "error": f"validate returned {resp.status}",
                        "url": url,
                        "response": payload,
                    }
    except Exception as e:
        return {"error": f"detections validate request failed: {e}", "url": url}

    # The detection_gui endpoint returns {results: [...], summary: {...}}.
    summary = (payload or {}).get("summary") or {}
    results = (payload or {}).get("results") or []
    coverage = summary.get("mean_coverage")
    if coverage is None and isinstance(summary.get("coverage_pct"), (int, float)):
        coverage = summary["coverage_pct"]

    per_link = []
    for r in results:
        # detection_svc returns dataclass dumps; defensive against shape drift.
        per_link.append({
            "link_id": r.get("link_id") if isinstance(r, dict) else None,
            "matching_rules": (r or {}).get("matching_rules") if isinstance(r, dict) else None,
            "coverage_score": (r or {}).get("coverage_score") if isinstance(r, dict) else None,
        })

    return {
        "operation_id": operation_id,
        "coverage_pct": coverage,
        "links_validated": len(per_link),
        "summary": summary,
        "per_link": per_link,
        "response": payload,
    }


@mcp.tool(name="cti_pipeline_wait_for_agents")
async def wait_for_agents(
    min_count: int = 1,
    timeout_s: int = 600,
    poll_interval_s: int = 30,
    platforms: Optional[list] = None,
) -> dict:
    """Block until at least ``min_count`` agents check into Caldera.

    Wraps GET /api/v2/agents in a poll loop so the planner doesn't
    have to choose between guessing-a-sleep and giving-up-on-empty-list.
    Returns as soon as the threshold is met OR the deadline lapses.

    Args:
        min_count: how many distinct agents (by paw) need to be present
            before the wait succeeds. Default 1.
        timeout_s: hard ceiling on total wait time. Default 600s.
        poll_interval_s: seconds between polls. Default 30s.
        platforms: optional list of platform strings (e.g. ["windows",
            "linux"]) — only agents matching one of these count toward
            min_count. ``None`` (default) accepts any platform.

    Returns:
        {agent_count, paws, hostnames, platforms, elapsed_s, timed_out}
    """
    import aiohttp
    import time as _time
    if min_count < 1:
        min_count = 1
    if timeout_s < 1:
        timeout_s = 1
    if poll_interval_s < 1:
        poll_interval_s = 1
    wanted = set(p.lower() for p in (platforms or []) if isinstance(p, str))

    url = _caldera_base_url().rstrip("/") + "/agents"
    deadline = _time.time() + timeout_s
    last_count = 0
    last_paws: list = []
    last_hosts: list = []
    last_plats: list = []
    while _time.time() < deadline:
        try:
            async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        agents = json.loads(await resp.text()) or []
                        if wanted:
                            agents = [a for a in agents
                                      if (a.get("platform") or "").lower() in wanted]
                        last_paws = [a.get("paw") for a in agents if a.get("paw")]
                        last_hosts = [a.get("host") for a in agents if a.get("host")]
                        last_plats = sorted({(a.get("platform") or "").lower()
                                              for a in agents if a.get("platform")})
                        last_count = len(last_paws)
                        if last_count >= min_count:
                            return {
                                "agent_count": last_count,
                                "paws": last_paws,
                                "hostnames": last_hosts,
                                "platforms": last_plats,
                                "elapsed_s": int(timeout_s - max(0, deadline - _time.time())),
                                "timed_out": False,
                            }
        except Exception as e:
            log.warning("wait_for_agents poll error: %r", e)
        await asyncio.sleep(poll_interval_s)
    return {
        "agent_count": last_count,
        "paws": last_paws,
        "hostnames": last_hosts,
        "platforms": last_plats,
        "elapsed_s": timeout_s,
        "timed_out": True,
        "error": f"only {last_count} agents checked in within {timeout_s}s (wanted {min_count})",
    }



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # cti_pipeline_stage1's ProcessPoolExecutor spawns workers as
    # `python mcp_server.py --multiprocessing-fork ...`. Each worker
    # imports this module and would call `mcp.run()` here, which
    # blocks on stdin reading JSON-RPC that the multiprocessing
    # bootstrap never sends. `freeze_support()` detects the
    # `--multiprocessing-fork` marker, runs the worker bootstrap
    # (which exits when the worker function returns), and is a no-op
    # in the genuine main process. So mcp.run() below only ever fires
    # for the real stdio entry point.
    import multiprocessing as _mp
    _mp.freeze_support()
    mcp.run()
