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
        "range topology SDO -> deploy spec -> range deploy -> operation "
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
    endpoints like /plugin/range/onprem/manage/deploy that live outside
    the v2 API namespace.
    """
    api = _caldera_base_url()
    # api looks like "http://host:port/api/v2/"; strip the trailing
    # "api/v2/" to get the root.
    for marker in ("api/v2/", "api/v2"):
        if api.endswith(marker):
            return api[: -len(marker)]
    # Fallback - use the scheme+host only.
    return api


def _image_catalog_key(img: dict) -> tuple[str, str, str]:
    return (
        str(img.get("name") or "").lower(),
        str(img.get("provider") or "").lower(),
        str(img.get("file") or "").lower(),
    )


def _caldera_root_candidates() -> list[str]:
    roots = [_caldera_root().rstrip("/")]
    try:
        import yaml  # type: ignore
        for candidate in (Path("conf/local.yml"), Path("conf/default.yml")):
            if not candidate.is_file():
                continue
            doc = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            http = str(doc.get("app.contact.http") or "").strip()
            if http:
                roots.append(http.rstrip("/").replace("0.0.0.0", "127.0.0.1"))
                continue
            port = doc.get("port")
            if port:
                roots.append(f"http://127.0.0.1:{port}")
    except Exception as e:
        log.debug(f"Caldera root candidate load failed: {e}")
    out: list[str] = []
    seen: set[str] = set()
    for root in roots:
        root = root.rstrip("/")
        if root and root not in seen:
            seen.add(root)
            out.append(root)
    return out


def _merge_image_record(images: list, seen: dict, img: dict) -> None:
    key = _image_catalog_key(img)
    existing = seen.get(key)
    if existing is None:
        seen[key] = img
        images.append(img)
        return
    for field, value in img.items():
        if existing.get(field) in (None, "", [], {}):
            existing[field] = value


def _file_images_catalog() -> list:
    images: list = []
    seen: dict[tuple[str, str, str], dict] = {}
    try:
        import yaml  # type: ignore
        for candidate in (
            Path("plugins/range/conf/onprem_microvm_images.yml"),
            Path("plugins/range/conf/onprem_images.yml"),
        ):
            if not candidate.is_file():
                continue
            doc = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            for img in doc.get("images") or []:
                if not isinstance(img, dict):
                    continue
                rec = dict(img)
                rec.setdefault("_source_catalog", str(candidate))
                _merge_image_record(images, seen, rec)
    except Exception as e:
        log.debug(f"file image catalog load failed: {e}")
    return images


async def _range_api_images_catalog(provider: str = "microvm") -> list:
    body: dict = {}
    try:
        import aiohttp
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            for root in _caldera_root_candidates():
                url = f"{root}/plugin/range/onprem/images"
                try:
                    async with session.get(
                        url,
                        params={"provider": provider},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        body = await resp.json(content_type=None)
                        break
                except Exception as e:
                    log.debug(f"Range image API attempt failed at {url}: {e}")
    except Exception as e:
        log.debug(f"Range image API catalog load failed: {e}")
        return []
    if not body:
        return []

    out: list = []
    for img in body.get("images") or []:
        if not isinstance(img, dict):
            continue
        rec = dict(img)
        rec.setdefault("provider", provider)
        rec.setdefault("bootstrapped", True)
        rec.setdefault("_source_catalog", f"range-api:{provider}")
        out.append(rec)
    return out


async def _range_get_json(path: str, params: dict | None = None,
                          timeout_s: int = 10) -> dict:
    try:
        import aiohttp
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            for root in _caldera_root_candidates():
                url = f"{root}{path}"
                try:
                    async with session.get(
                        url,
                        params=params or {},
                        timeout=aiohttp.ClientTimeout(total=timeout_s),
                    ) as resp:
                        if resp.status >= 400:
                            continue
                        return await resp.json(content_type=None) or {}
                except Exception as e:
                    log.debug(f"Range GET failed at {url}: {e}")
    except Exception as e:
        log.debug(f"Range GET setup failed for {path}: {e}")
    return {}


async def _range_post_json(path: str, body: dict | None = None,
                           timeout_s: int = 10) -> dict:
    try:
        import aiohttp
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            for root in _caldera_root_candidates():
                url = f"{root}{path}"
                try:
                    async with session.post(
                        url,
                        json=body or {},
                        timeout=aiohttp.ClientTimeout(total=timeout_s),
                    ) as resp:
                        text = await resp.text()
                        try:
                            payload = json.loads(text) if text else {}
                        except json.JSONDecodeError:
                            payload = {"raw": text}
                        if resp.status >= 400:
                            payload.setdefault("error", f"HTTP {resp.status}")
                        return payload
                except Exception as e:
                    log.debug(f"Range POST failed at {url}: {e}")
    except Exception as e:
        log.debug(f"Range POST setup failed for {path}: {e}")
    return {}


async def _load_images_catalog() -> list:
    images: list = []
    seen: dict[tuple[str, str, str], dict] = {}
    for rec in await _range_api_images_catalog("microvm"):
        _merge_image_record(images, seen, rec)
    for rec in _file_images_catalog():
        _merge_image_record(images, seen, rec)
    return images


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

    images_catalog = await _load_images_catalog()

    try:
        topology = build_range_topology(bundle, taxonomy, images_catalog)
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
                images_catalog,
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

        images_catalog = await _load_images_catalog()

        topology = build_range_topology(fused, taxonomy, images_catalog)
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
                    images_catalog,
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


@mcp.tool(name="cti_pipeline_synthesize_deploy_spec")
@_stdout_safe
async def synthesize_deploy_spec_tool(
    topology_path: str,
    ae_plan_slug: Optional[str] = None,
) -> dict:
    """Synthesise a range-plugin deploy spec from a topology SDO + AE plan.

    Merges the topology SDO's hosts + identities with an AE-library plan
    (matched by adversary slug when provided, otherwise by the topology's
    own ``x_ae_library_match`` block when stage 4 already wrote one).

    Args:
        topology_path: absolute or repo-relative path to a
            ``*.topology.json`` file produced by build_topology /
            ingest_cti.
        ae_plan_slug: optional CTID adversary slug
            (e.g. "alphv_blackcat"). When unset the tool tries
            topology.x_ae_library_match.adversary first, then leaves the
            AE-IR slot empty (topology-only synthesis).

    Returns:
        {profile, provider, images, users, domain, post_deploy_steps,
         feature_playbooks, elk_host, saved_to}
    """
    from plugins.mcp.app.utilities.cti_deploy_spec import synthesize_deploy_spec

    if not topology_path:
        return {"error": "topology_path is required"}
    p = _resolve_pipeline_file(topology_path, data_subdirs=("outputs_topology",))
    if not p.is_file():
        return {"error": f"topology_path not found: {topology_path}"}

    try:
        topo = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"failed to parse topology JSON: {e}"}

    # Resolve the AE plan slug: explicit arg wins, else the topology's
    # own match block, else leave AE IR empty.
    if not ae_plan_slug:
        match = topo.get("x_ae_library_match") if isinstance(topo, dict) else None
        if isinstance(match, dict):
            ae_plan_slug = (match.get("adversary") or "").strip() or None

    ae_ir: Optional[dict] = None
    if ae_plan_slug:
        try:
            from plugins.mcp.app.utilities.cti_ae_library_loader import (
                discover_ae_plans,
                find_plan_by_adversary,
                parse_ae_plan,
            )
            plans = discover_ae_plans()
            plan = find_plan_by_adversary(plans, ae_plan_slug)
            if plan:
                ae_ir = parse_ae_plan(plan, taxonomy=None)
        except Exception as e:
            log.warning(f"AE plan IR not loaded for slug {ae_plan_slug!r}: {e}")

    images_catalog = await _load_images_catalog()

    try:
        spec = synthesize_deploy_spec(
            topo,
            ae_plan_ir=ae_ir,
            images_catalog=images_catalog or None,
        )
    except Exception as e:
        log.exception("synthesize_deploy_spec failed")
        return {"error": f"deploy-spec synthesis failed: {e}"}

    # Persist for the deploy_range tool / external callers.
    out_path = p.parent / f"{p.stem.replace('.topology', '')}.deploy_spec.json"
    try:
        out_path.write_text(
            json.dumps(spec, indent=2, default=str), encoding="utf-8",
        )
    except Exception as e:
        log.warning(f"could not persist deploy_spec to {out_path}: {e}")

    return {
        "profile": spec.get("profile"),
        "provider": spec.get("provider"),
        "image_count": len(spec.get("images") or []),
        "images": spec.get("images") or [],
        "users": spec.get("users") or [],
        "domain": spec.get("domain"),
        "feature_playbooks": spec.get("feature_playbooks") or [],
        "elk_host": spec.get("elk_host"),
        "post_deploy_steps": spec.get("post_deploy_steps") or [],
        "software_install_requests": spec.get("software_install_requests") or [],
        "required_platforms_missing": spec.get("required_platforms_missing") or [],
        "operator_review": spec.get("operator_review") or {},
        "ae_plan_slug": ae_plan_slug,
        "saved_to": str(out_path),
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


@mcp.tool(name="cti_pipeline_range_capabilities")
async def range_capabilities(provider: Optional[str] = None) -> dict:
    """Return live Range provider, image, feature, and substrate data.

    Provider names come from Range's live provider endpoint, which reads
    SUPPORTED_PROVIDERS, instead of from a static MCP-side list.
    """
    providers_payload = await _range_get_json("/plugin/range/onprem/providers")
    providers = providers_payload.get("providers") or []
    selected = (provider or "").strip()
    if not selected and providers:
        selected = str(providers[0].get("name") or providers[0].get("provider") or "")

    images = await _range_api_images_catalog(selected) if selected else []
    features = await _range_get_json("/plugin/range/onprem/features")
    substrate = {}
    if selected == "microvm":
        substrate = await _range_get_json("/plugin/range/microvm/substrate-status")

    return {
        "providers": providers,
        "selected_provider": selected,
        "images": images,
        "image_count": len(images),
        "features": features,
        "microvm_substrate": substrate,
    }


@mcp.tool(name="cti_pipeline_wait_for_range")
async def wait_for_range(profile_name: str, provider: str = "microvm",
                         timeout_s: int = 1200,
                         poll_interval_s: int = 15) -> dict:
    """Poll Range deployment status until the range is ready or failed."""
    import time as _time

    if not profile_name:
        return {"error": "profile_name is required"}
    if timeout_s < 1:
        timeout_s = 1
    if poll_interval_s < 1:
        poll_interval_s = 1

    terminal_ok = {"running", "ready", "complete", "completed", "success"}
    terminal_bad = {"error", "failed", "failure"}
    deadline = _time.time() + timeout_s
    polls = 0
    last: dict = {}

    while _time.time() <= deadline:
        polls += 1
        last = await _range_post_json(
            "/plugin/range/onprem/deploy-status",
            {"profile": profile_name, "provider": provider or "microvm"},
            timeout_s=15,
        )
        status = str(last.get("status") or "unknown").lower()
        elapsed = int(timeout_s - max(0, deadline - _time.time()))
        if status in terminal_ok:
            return {
                "profile": profile_name,
                "provider": provider,
                "status": status,
                "ready": True,
                "timed_out": False,
                "elapsed_s": elapsed,
                "polls": polls,
                "last_status": last,
            }
        if status in terminal_bad:
            return {
                "profile": profile_name,
                "provider": provider,
                "status": status,
                "ready": False,
                "timed_out": False,
                "elapsed_s": elapsed,
                "polls": polls,
                "last_status": last,
                "error": last.get("error"),
            }
        await asyncio.sleep(poll_interval_s)

    return {
        "profile": profile_name,
        "provider": provider,
        "status": str(last.get("status") or "unknown").lower(),
        "ready": False,
        "timed_out": True,
        "elapsed_s": timeout_s,
        "polls": polls,
        "last_status": last,
        "error": f"range did not become ready within {timeout_s}s",
    }


@mcp.tool(name="cti_pipeline_import_ansible_feature")
async def import_ansible_feature(feature_name: str, main_yml: str,
                                 extra_files: Optional[dict] = None,
                                 profile_name: Optional[str] = None,
                                 provider: str = "microvm") -> dict:
    """Import a custom Range Ansible feature for later deployment.

    Wraps Range's existing /plugin/range/onprem/import-ansible-feature
    endpoint. Use this only when CTI requires a service/configuration and
    cti_pipeline_range_capabilities shows no existing feature playbook
    can satisfy it.

    Args:
        feature_name: feature slug accepted by Range (letters, numbers,
            hyphens, underscores).
        main_yml: content for the feature's main.yml playbook.
        extra_files: optional mapping of relative filename -> text content
            for roles, templates, files, vars, etc.
        profile_name: optional Range profile context.
        provider: optional Range provider context.

    Returns:
        Range import response with status, feature_name, warnings/message.
    """
    if not feature_name:
        return {"error": "feature_name is required"}
    if not main_yml:
        return {"error": "main_yml is required"}
    if extra_files is not None and not isinstance(extra_files, dict):
        return {"error": "extra_files must be a mapping of filename to content"}

    import aiohttp

    url = _caldera_root().rstrip("/") + "/plugin/range/onprem/import-ansible-feature"
    headers = {
        "KEY": _caldera_api_key(),
        "Accept": "application/json",
    }
    form = aiohttp.FormData()
    form.add_field("feature_name", feature_name)
    if profile_name:
        form.add_field("profile", profile_name)
    if provider:
        form.add_field("provider", provider)
    form.add_field(
        "files",
        main_yml.encode("utf-8"),
        filename="main.yml",
        content_type="application/x-yaml",
    )
    for filename, content in (extra_files or {}).items():
        if not filename:
            continue
        data = content if isinstance(content, bytes) else str(content).encode("utf-8")
        form.add_field(
            "files",
            data,
            filename=str(filename),
            content_type="application/octet-stream",
        )

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                url,
                data=form,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"raw": text}
                if resp.status >= 400:
                    return {
                        "error": f"feature import returned {resp.status}",
                        "url": url,
                        "response": payload,
                    }
                return payload
    except Exception as e:
        return {"error": f"feature import request failed: {e}", "url": url}


@mcp.tool(name="cti_pipeline_deploy_range")
async def deploy_range(profile_name: str, deploy_spec: dict) -> dict:
    """POST a deploy spec to the range plugin and return its accept response.

    The range plugin's /plugin/range/onprem/manage/deploy endpoint is
    fire-and-forget: it returns 202-style "accepted" and runs the deploy
    in the background. Callers should poll
    /plugin/range/onprem/deploy-status (or call this server's
    operation tools later) to track progress.

    Args:
        profile_name: stamp the spec's profile to this name. Prevents
            collisions when running multiple emulations against the same
            range plugin.
        deploy_spec: a deploy spec dict (typically the output of
            cti_pipeline_synthesize_deploy_spec). Required keys:
            ``provider``, ``images``.

    Returns:
        {stack_id, status, response} - status comes from the range
        endpoint's reply; stack_id mirrors how the range plugin keys
        _deploy_status[].
    """
    if not profile_name:
        return {"error": "profile_name is required"}
    if not isinstance(deploy_spec, dict):
        return {"error": "deploy_spec must be a dict"}

    provider = (deploy_spec.get("provider") or "").strip() or "microvm"
    images = deploy_spec.get("images") or []
    if not images:
        return {"error": "deploy_spec.images is empty - nothing to deploy"}

    # Use aiohttp - we are inside an asyncio loop and the parent process
    # already requires it.
    import aiohttp

    # Auto-register the synthesised profile before deploying. The range
    # plugin's save-profile endpoint is idempotent (dedups by profile
    # name) so calling it on every deploy is safe and avoids the
    # "Profile 'X' not found" silent fail-loop. For microvm, we inject
    # the canonical timestone endpoint + db url so the provider boots.
    save_url = _caldera_root().rstrip("/") + "/plugin/range/onprem/save-profile"
    profile_yaml = (
        f"- profile: {profile_name}\n"
        f"  range: onprem\n"
        f"  provider: {provider}\n"
    )
    if provider == "microvm":
        profile_yaml += (
            "  timestone_endpoint: localhost:50051\n"
            "  timestone_database_url: "
            "postgres://timestone@127.0.0.1:5433/timestone\n"
            "  vars: {}\n"
        )
    else:
        profile_yaml += "  vars: {}\n"
    try:
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            async with session.post(
                save_url,
                json={"yaml": profile_yaml},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                save_text = await resp.text()
                if resp.status >= 400:
                    # Profile registration failed — surface the error
                    # immediately instead of letting deploy hit the
                    # same "profile not found" trap.
                    return {
                        "error": f"profile register returned {resp.status}",
                        "url": save_url,
                        "response": save_text[:500],
                    }
    except Exception as e:
        return {"error": f"profile register request failed: {e}", "url": save_url}

    body = {
        "profile": profile_name,
        "provider": provider,
        "images": images,
    }

    url = _caldera_root().rstrip("/") + "/plugin/range/onprem/manage/deploy"
    try:
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"raw": text}
                if resp.status >= 400:
                    return {
                        "error": f"range deploy returned {resp.status}",
                        "url": url,
                        "response": payload,
                    }
    except Exception as e:
        return {"error": f"range deploy request failed: {e}", "url": url}

    # Best-effort stack_id reconstruction mirrors sanitize_stack_id in
    # plugins/range/app/cdktf/cdktf_utilities.py - a slug-and-lowercase
    # join of provider + profile. We avoid importing it here so the MCP
    # subprocess does not need the range plugin on its sys.path.
    import re
    stack_id = re.sub(r"[^a-z0-9-]+", "-",
                      f"{provider}-{profile_name}".lower()).strip("-")

    return {
        "stack_id": stack_id,
        "status": (payload or {}).get("status", "accepted"),
        "provider": provider,
        "profile": profile_name,
        "image_count": len(images),
        "response": payload,
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
        # group membership which the range plugin / sandcat agents
        # already apply.
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


@mcp.tool(name="cti_pipeline_apply_features")
async def apply_features(
    profile_name: str,
    provider: str = "microvm",
    vm_features: Optional[dict] = None,
    apply_defaults: bool = True,
) -> dict:
    """Apply Range feature playbooks to deployed microVMs.

    Wraps POST /plugin/range/onprem/add-features-to-vm — the same
    endpoint the Range UI uses to install winlogbeat / sysmon /
    auditbeat / etc. on already-deployed VMs. Telemetry shippers are
    what give the detections plugin real process-execution logs to
    correlate against; without them the SIEM only sees sandcat
    marker lines.

    Args:
        profile_name: the deploy profile the VMs belong to.
        provider: the range provider (default ``microvm``).
        vm_features: optional explicit ``{vm_name: [feature, ...]}``
            map. When omitted (or paired with ``apply_defaults=True``),
            the tool fans out the canonical defaults based on each
            VM's reported OS:
              * Windows -> winlogbeat + sysmon
              * Linux   -> (no feature ships by default today; the
                           Range plugin's auditbeat role is not
                           registered as a feature playbook yet)
        apply_defaults: when True (default), merge the per-OS defaults
            into vm_features for any VM not explicitly listed.

    Returns:
        {results: [{vm_name, features, ok, response, error?}, ...],
         total_vms, succeeded, failed}
    """
    import aiohttp
    if not profile_name:
        return {"error": "profile_name is required"}
    vm_features = dict(vm_features or {})

    # Discover the VMs from /tmp/timestone-microvms/<id>/meta.json so
    # we can fan out features per-OS without the caller needing to
    # know the deployed inventory.
    microvm_base = Path(os.environ.get(
        "TIMESTONE_MICROVM_RUNTIME_BASE", "/tmp/timestone-microvms"
    ))
    discovered: list[dict] = []
    if microvm_base.is_dir():
        for d in sorted(microvm_base.iterdir()):
            meta = d / "meta.json"
            if not meta.is_file():
                continue
            try:
                m = json.loads(meta.read_text())
                discovered.append({
                    "vm_name": m.get("vm_name") or d.name,
                    "os": (m.get("os") or "").lower(),
                })
            except Exception:
                continue

    if apply_defaults:
        for vm in discovered:
            name = vm["vm_name"]
            os_kind = vm["os"]
            defaults: list = []
            if os_kind == "windows":
                defaults = ["winlogbeat", "sysmon"]
            # Linux gets no feature defaults today — auditbeat ships
            # as a role, not a feature playbook. The deploy spec
            # can author + upload one via
            # cti_pipeline_import_ansible_feature when evidence is specific.
            if name not in vm_features and defaults:
                vm_features[name] = defaults

    if not vm_features:
        return {
            "results": [], "total_vms": len(discovered),
            "succeeded": 0, "failed": 0,
            "note": "no features to apply (no windows VMs and no explicit vm_features)",
        }

    url = _caldera_root().rstrip("/") + "/plugin/range/onprem/add-features-to-vm"
    results = []
    succeeded = 0
    failed = 0
    async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
        for vm_name, features in vm_features.items():
            if not features:
                continue
            body = {
                "profile": profile_name,
                "provider": provider,
                "vm_name": vm_name,
                "new_features": list(features),
            }
            entry = {"vm_name": vm_name, "features": list(features)}
            try:
                async with session.post(
                    url, json=body,
                    timeout=aiohttp.ClientTimeout(total=900),
                ) as resp:
                    text = await resp.text()
                    try:
                        payload = json.loads(text) if text else {}
                    except json.JSONDecodeError:
                        payload = {"raw": text}
                    if resp.status >= 400:
                        entry["ok"] = False
                        entry["error"] = (payload or {}).get("error") or f"HTTP {resp.status}"
                        failed += 1
                    else:
                        entry["ok"] = True
                        entry["response"] = payload
                        succeeded += 1
            except Exception as e:
                entry["ok"] = False
                entry["error"] = str(e)
                failed += 1
            results.append(entry)

    return {
        "results": results,
        "total_vms": len(discovered),
        "succeeded": succeeded,
        "failed": failed,
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
