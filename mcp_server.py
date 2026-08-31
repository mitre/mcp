"""cti_pipeline MCP server.

Exposes the deterministic CTI -> STIX -> operation pipeline as MCP tools
so plan_execute (and any other DSPy ReAct workflow) can drive the same
artefacts via tool calls instead of a parallel hard-coded workflow.

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
from typing import Optional

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
    "default_enabled": False,
    "description": (
        "End-to-end CTI ingest tools: PDF/HTML -> STIX 2.1 bundle -> "
        "adversary -> operation. Thin wrappers over the deterministic "
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




# ---------------------------------------------------------------------------
# Pipeline tools
# ---------------------------------------------------------------------------

@mcp.tool(name="cti_pipeline_ingest_cti")
@_stdout_safe
async def ingest_cti(file_path: str) -> dict:
    """Run the full CTI ingest pipeline (raw -> STIX) on a file.

    Stages 1 and 2 (cleaning, IR extraction, STIX assembly) run in order.
    The file is copied into the plugin's data/raw/uploads/ directory first
    so the pipeline's working tree stays canonical.

    Args:
        file_path: absolute or repo-relative path to a CTI document
            (PDF, HTML, plaintext). Mandatory.

    Returns:
        {stix_path, counts} where counts breaks down the bundle by SDO
        type (attack_patterns, threat_actors).
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

    def _matches_stem(p: Path) -> bool:
        s_norm = "".join(c for c in stem.lower() if c.isalnum())
        n_norm = "".join(c for c in p.stem.lower() if c.isalnum())
        return bool(s_norm) and s_norm in n_norm

    stix_path: Optional[Path] = None
    if outputs_stix.is_dir():
        for p in outputs_stix.glob("*.stix.json"):
            if _matches_stem(p):
                stix_path = p
                break

    counts = {
        "attack_patterns": 0,
        "threat_actors": 0,
    }
    if stix_path and stix_path.is_file():
        try:
            bundle = json.loads(stix_path.read_text(encoding="utf-8"))
            for obj in bundle.get("objects", []):
                t = obj.get("type", "")
                if t == "attack-pattern":
                    counts["attack_patterns"] += 1
                elif t == "threat-actor":
                    counts["threat_actors"] += 1
        except Exception as e:
            log.warning(f"counts assembly failed: {e}")

    return {
        "input": str(src),
        "filename": src.name,
        "stix_path": str(stix_path) if stix_path else None,
        "counts": counts,
        "state": svc.status(),
    }


@mcp.tool(name="cti_pipeline_fuse")
@_stdout_safe
async def fuse_cti_bundles(stix_paths: list[str]) -> dict:
    """Fuse multiple STIX bundles into one merged bundle.

    Bundles are merged by canonical identifiers: MITRE ATT&CK IDs, CVEs,
    CPEs, and normalized STIX names. Relationships are remapped to the
    surviving object IDs.
    """
    from plugins.mcp.app.utilities.cti_fusion import fuse_bundles

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

    return {
        "source_count": len(bundles),
        "object_count": len(fused.get("objects") or []),
        "saved_to": str(out_path),
    }


def _bundle_technique_ids(bundle: dict) -> list[str]:
    """ATT&CK ids from a bundle's attack-patterns, keyed on external_references.

    STIX object ids regenerate every run, so external_id is the only stable key.
    """
    out = []
    if not isinstance(bundle, dict):
        return out
    for o in bundle.get("objects", []) or []:
        if not isinstance(o, dict) or o.get("type") != "attack-pattern":
            continue
        for ref in o.get("external_references", []) or []:
            if (ref.get("source_name") or "").lower() != "mitre-attack":
                continue
            eid = (ref.get("external_id") or "").strip()
            if eid.startswith("T"):
                out.append(eid)
    return sorted(set(out))


def _bundle_actor_name(bundle: dict) -> Optional[str]:
    if not isinstance(bundle, dict):
        return None
    for o in bundle.get("objects", []) or []:
        if not isinstance(o, dict):
            continue
        if o.get("type") in ("threat-actor", "intrusion-set") and o.get("name"):
            return str(o["name"])
    return None


# atomic_ordering is executed top to bottom, so an unordered list encrypts the
# estate before it persists on it. Rank by the ability's ATT&CK technique
# rather than its CALDERA tactic: CALDERA's vocabulary is its own, and its
# three most common values (multiple, stealth, defense-impairment) have no
# ATT&CK counterpart, so 43 percent of the stockpile would tie for last.
# The sequence comes from the bundle's x-mitre-matrix, so it tracks whatever
# ATT&CK version is installed rather than a copy that silently goes stale.


def _technique_rank(technique_id: str, taxonomy: dict) -> int:
    """Earliest kill-chain phase this technique belongs to.

    A technique can span phases (T1547.001 is persistence and
    privilege-escalation); the earliest is the one that has to run first.
    """
    kill_chain = taxonomy.get("kill_chain_order") or ()
    entry = (taxonomy.get("attack_id_index") or {}).get((technique_id or "").strip())
    if not entry:
        parent = (technique_id or "").split(".")[0]
        entry = (taxonomy.get("attack_id_index") or {}).get(parent)
    ranks = [
        kill_chain.index(p["phase_name"])
        for p in (entry or {}).get("kill_chain_phases") or []
        if p.get("kill_chain_name") == "mitre-attack"
        and p.get("phase_name") in kill_chain
    ]
    return min(ranks) if ranks else len(kill_chain)


def _technique_matches(report_id: str, ability_id: str) -> bool:
    """A report naming T1059 should reach T1059.001 abilities and vice versa.

    Reports and the stockpile disagree on granularity often enough that an
    exact match alone understates the coverage the operator has. Only
    parent-to-child counts: T1059.001 and T1059.003 are siblings, and
    treating them as equivalent would run the wrong technique.
    """
    if report_id == ability_id:
        return True
    return (report_id == ability_id.split(".")[0]
            or ability_id == report_id.split(".")[0])


@mcp.tool(name="cti_pipeline_build_adversary")
@_stdout_safe
async def build_adversary(stix_path: str, platforms: Optional[list] = None,
                          name: Optional[str] = None, commit: bool = False,
                          max_per_technique: int = 3) -> dict:
    """Build a CALDERA adversary from the techniques in a STIX bundle.

    Maps each ATT&CK technique in the bundle to the abilities that implement
    it, scoped to the platforms your agents actually run. Reports what it
    could not cover instead of silently dropping it.

    Args:
        stix_path: path to a stage 2 STIX bundle.
        platforms: platforms to scope abilities to (e.g. ["windows"]).
            Defaults to the platforms of agents that have checked in.
        name: adversary name. Defaults to the bundle's threat actor,
            then the file stem.
        commit: create the adversary. Leave false to preview.
        max_per_technique: abilities to keep per technique. A single
            technique can have 90+ implementations across the atomic
            plugin, which makes an adversary that runs for hours. Raise it
            for breadth; ability_count_available reports what was capped.

    Returns:
        {name, matched, unmatched_techniques, platform_excluded,
         technique_count, ability_count, ability_count_available,
         committed, adversary_id}
        matched              - ability ids that will run
        unmatched_techniques - technique ids with no ability at all
        platform_excluded    - an ability exists but no live agent can run it
    """
    if not stix_path:
        return {"error": "stix_path is required"}
    p = _resolve_pipeline_file(stix_path, data_subdirs=("outputs_stix", "stix_cti"))
    if not p.is_file():
        return {"error": f"stix bundle not found: {stix_path}"}

    try:
        bundle = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"could not read {p}: {e}"}

    techniques = _bundle_technique_ids(bundle)
    if not techniques:
        return {"error": f"no ATT&CK techniques in {p.name}; nothing to build from"}

    import aiohttp

    wanted = {str(x).lower().strip() for x in (platforms or []) if x}
    if not wanted:
        # A report says what to run; only live agents say where. Guessing here
        # yields a full-looking adversary that runs nothing.
        url = _caldera_base_url() + "agents"
        try:
            async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return {"error": f"reading agents returned {resp.status}; "
                                         f"cannot determine platforms"}
                    agents = json.loads(await resp.text() or "[]")
        except Exception as e:
            return {"error": f"could not read agents to determine platforms: {e}"}
        wanted = {(a.get("platform") or "").lower() for a in agents if a.get("platform")}
        if not wanted:
            return {"error": "no agents have checked in, so no platform is known. "
                             "Deploy an agent, or pass platforms explicitly to preview."}

    url = _caldera_base_url() + "abilities"
    try:
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    # Collapsing this to an empty list reports a broken API
                    # key as "the stockpile covers none of this report".
                    return {"error": f"reading abilities returned {resp.status}"}
                abilities = json.loads(await resp.text() or "[]")
    except Exception as e:
        return {"error": f"could not read abilities: {e}"}

    by_technique: dict[str, list[str]] = {}
    technique_of: dict[str, str] = {}
    covered: set[str] = set()
    excluded_techniques: set[str] = set()
    available = 0
    for ab in sorted(abilities, key=lambda a: str(a.get("ability_id") or "")):
        tid = (ab.get("technique_id") or "").strip()
        ability_id = ab.get("ability_id")
        if not tid or not ability_id:
            continue
        hits = [t for t in techniques if _technique_matches(t, tid)]
        if not hits:
            continue
        ab_platforms = {(ex.get("platform") or "").lower()
                        for ex in (ab.get("executors") or []) if ex.get("platform")}
        if ab_platforms and not (ab_platforms & wanted):
            excluded_techniques.update(hits)
            continue
        available += 1
        covered.update(hits)
        technique_of[ability_id] = tid
        # Bucket under every technique the ability covers, not just the first.
        # A bundle naming both a parent and its sub-techniques otherwise puts
        # them all in one bucket, so the cap starves every technique but one.
        for hit in hits:
            bucket = by_technique.setdefault(hit, [])
            if len(bucket) < max(1, max_per_technique):
                bucket.append(ability_id)

    matched = list(dict.fromkeys(
        aid for tid in sorted(by_technique) for aid in by_technique[tid]
    ))
    try:
        from plugins.mcp.app.utilities.cti_taxonomy_loader import load_mitre_taxonomy
        taxonomy = load_mitre_taxonomy()
    except Exception as e:
        log.warning("kill-chain ordering unavailable: %r", e)
        taxonomy = {}
    # Stable within a phase so the selection stays reproducible.
    matched.sort(key=lambda aid: (_technique_rank(technique_of.get(aid, ""), taxonomy), aid))
    unmatched = sorted(set(techniques) - covered - excluded_techniques)
    platform_excluded = sorted(excluded_techniques - covered)

    adv_name = name or _bundle_actor_name(bundle) or p.name.replace(".stix.json", "")
    result = {
        "name": adv_name,
        "platforms": sorted(wanted),
        "technique_count": len(techniques),
        "ability_count": len(matched),
        "ability_count_available": available,
        "matched": matched,
        "unmatched_techniques": unmatched,
        "platform_excluded": platform_excluded,
        "committed": False,
        "stix_path": str(p),
    }
    if not commit:
        return result
    if not matched:
        return {**result, "error": "no ability matched any technique; nothing to commit"}

    body = {
        "name": adv_name,
        "description": f"Built from {p.name} ({len(matched)} abilities, "
                       f"{len(techniques)} techniques)",
        "atomic_ordering": matched,
    }
    url = _caldera_base_url() + "adversaries"
    try:
        async with aiohttp.ClientSession(headers=_caldera_headers()) as session:
            async with session.post(url, json=body,
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"raw": text}
                if resp.status >= 400:
                    return {**result, "error": f"adversary creation returned {resp.status}",
                            "response": payload}
    except Exception as e:
        return {**result, "error": f"adversary creation failed: {e}"}

    result["committed"] = True
    result["adversary_id"] = (payload or {}).get("adversary_id")
    return result


@mcp.tool(name="cti_pipeline_run_operation")
async def run_operation(
    adversary_id: str,
    agent_paws: list,
    operation_name: Optional[str] = None,
    source_id: Optional[str] = None,
) -> dict:
    """Start a Caldera v2 operation against an adversary using listed agents.

    Wraps POST /api/v2/operations. The v2 manager builds the operation
    using the same code path the GUI uses, so this tool is equivalent to
    clicking 'Run' on the operations page.

    Args:
        adversary_id: ID of the adversary to emulate.
        agent_paws: agents the caller intends to target. Recorded on the
            result for correlation only. Caldera scopes an operation by
            'group', and OperationSchema discards any other key, so this
            does NOT narrow the run. Every agent in the group takes part.
        operation_name: optional name; auto-generated when absent.
        source_id: optional fact source to seed the operation with. Defaults
            to Caldera's 'basic' source. Facts about the operator's own
            estate come from the operator, never from a threat report.

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
        "source": {"id": source_id or "basic"},
        "state": "running",
        "autonomous": 1,
        "auto_close": False,
        "obfuscator": "plain-text",
        "jitter": "2/4",
        "visibility": 51,
        "use_learning_parsers": True,
    }
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
        # Named for what it is: the caller's request, not an applied filter.
        "requested_paws": list(agent_paws),
        "group": body["group"],
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
