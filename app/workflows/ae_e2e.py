"""ae-e2e workflow.

In-process orchestrator for the full FULL-VISION pipeline. Twelve stages
that march from a single CTI document to a validated, detection-scored
operation, with each stage observing state via Caldera's ``services`` dict
rather than HTTP polling.

Stage order matches scripts/e2e_full_vision_lib.py so the legacy shell
script can hand off to / resume from the same checkpoint file
(``/tmp/e2e_full_vision_state.json``):

    preflight -> cti -> topology -> deploy_spec -> deploy -> meta ->
    sandcat -> agents -> adversary -> operation -> detections -> report

Differences vs. the shell script:

* deploy: calls ``range_svc.build_onprem(profile, images)`` directly and
  watches ``range_svc._deploy_status[stack_id]`` in-process. No HTTP poll
  parser, so the silent-hang bug the script hit is gone.
* adversary: stores ``Adversary`` straight into ``data_svc`` and locates
  abilities via ``data_svc.locate('abilities')``.
* operation: builds an ``Operation`` via the v2 ``OperationApiManager``
  helpers (same code path the REST API uses) and lets the data_svc run it.
* detections: calls ``detection_svc.validate_operation()`` directly. No
  Aiohttp roundtrip.
* sandcat: still shells out to ``ansible-playbook microvm-implant.yml``
  because the implant transport / inventory generation is bulk I/O work
  that gains nothing from being in-process. But the inventory itself is
  built from ``data_svc.locate('agents')`` + meta.json reads, never from
  an HTTP response.

The workflow exposes a single ``run()`` coroutine. The MCP API endpoint
``POST /plugin/mcp/workflows/run-ae-end-to-end`` thinly wraps it.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from plugins.mcp.app.config import caldera_connection
from plugins.mcp.app.workflows.base import Workflow

# Stage order is the contract with the shell script's state file. Adding /
# renaming a stage requires bumping the format and updating the script.
STAGES = [
    "preflight",
    "cti",
    "topology",
    "deploy_spec",
    "deploy",
    "meta",
    "sandcat",
    "agents",
    "adversary",
    "operation",
    "detections",
    "report",
]

# Match the shell script's checkpoint path so a partial run started by the
# shell can be resumed by an MCP run (or vice versa). Caller may override
# via the ``checkpoint_path`` kwarg.
_DEFAULT_CHECKPOINT = Path("/tmp/e2e_full_vision_state.json")
_DEFAULT_REPORT = Path("/tmp/e2e_full_vision_report.md")


def _iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class AEEndToEndWorkflow:
    """Full CTI -> STIX -> AE plan -> range deploy -> sandcat -> operation -> detections.

    Instantiated lazily at run time (see ``_workflow_runner`` below); the
    Workflow registration in this module only needs the ``run`` callable.
    """

    id = "ae-e2e"

    def __init__(self, services: dict):
        self.services = services
        self.log = logging.getLogger("plugins.mcp.ae_e2e")

    # ------------------------------------------------------------------
    # Checkpoint helpers.
    # ------------------------------------------------------------------
    def _load_state(self, path: Path) -> dict:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                self.log.warning(f"checkpoint unparseable ({path}): {e}; starting fresh")
        return {"started": _iso(), "stages": {}, "run_id": str(uuid.uuid4())}

    def _save_state(self, path: Path, state: dict) -> None:
        state["updated"] = _iso()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        except OSError as e:
            self.log.warning(f"failed to persist checkpoint to {path}: {e}")

    def _mark(self, state: dict, name: str, status: str, payload: Optional[dict] = None) -> None:
        rec = state["stages"].setdefault(name, {})
        rec["status"] = status
        rec[f"at_{status}"] = _iso()
        if payload is not None:
            rec["payload"] = payload

    # ------------------------------------------------------------------
    # Entry point.
    # ------------------------------------------------------------------
    async def run(
        self,
        *,
        cti_source: Optional[str] = None,
        profile_name: Optional[str] = None,
        dry_run: bool = False,
        start_stage: Optional[str] = None,
        only_stage: Optional[str] = None,
        checkpoint_path: Optional[str] = None,
        elk_url: Optional[str] = None,
        kibana_url: Optional[str] = None,
        microvm_base: Optional[str] = None,
        adversary_slug: str = "alphv_blackcat",
        agents_timeout: int = 600,
        operation_timeout: int = 1800,
        deploy_timeout: int = 1200,
        cti_timeout: int = 900,
        **_extra,
    ) -> dict:
        """Run the 12-stage pipeline end-to-end.

        cti_source: path (absolute or repo-relative) to a CTI document to
            upload. Required unless start_stage > 'cti' or a previous run's
            checkpoint already has a cti payload.
        profile_name: range deploy profile name to use. Defaults to
            ``e2e-blackcat-<timestamp>`` so concurrent runs don't collide
            on the onprem service's stack_id lookup.
        dry_run: when True, each stage records what it would do and
            returns a synthetic payload without touching the wider system.
        start_stage / only_stage: stage filters mirroring the shell
            script's ``--from`` / ``--only`` flags.
        checkpoint_path: override the default ``/tmp/e2e_full_vision_state.json``.
        """
        cp_path = Path(checkpoint_path) if checkpoint_path else _DEFAULT_CHECKPOINT
        state = self._load_state(cp_path)
        state["run_id"] = state.get("run_id") or str(uuid.uuid4())

        # Stash run-scoped knobs so individual stages can reach them. We
        # intentionally avoid passing them as positional args to every
        # stage method — they're sticky for the whole run.
        ctx = {
            "cti_source": cti_source,
            "profile_name": profile_name or f"e2e-ae-{int(time.time())}",
            "dry_run": bool(dry_run),
            "elk_url": elk_url or os.environ.get("ELK_URL", "http://192.168.66.1:9200"),
            "kibana_url": kibana_url or os.environ.get("KIBANA_URL", "http://192.168.66.1:5601"),
            "microvm_base": microvm_base or os.environ.get(
                "TIMESTONE_MICROVM_RUNTIME_BASE", "/tmp/timestone-microvms"
            ),
            "adversary_slug": adversary_slug,
            "agents_timeout": int(agents_timeout),
            "operation_timeout": int(operation_timeout),
            "deploy_timeout": int(deploy_timeout),
            "cti_timeout": int(cti_timeout),
        }

        if only_stage:
            order = [only_stage]
        else:
            start_idx = STAGES.index(start_stage) if start_stage else 0
            order = STAGES[start_idx:]

        for name in order:
            if name not in STAGES:
                raise ValueError(f"unknown stage {name!r}; valid: {STAGES}")
            self.log.info(f"[ae-e2e] stage={name} dry_run={ctx['dry_run']}")
            self._mark(state, name, "running")
            self._save_state(cp_path, state)
            try:
                method = getattr(self, f"_stage_{name}")
                payload = await method(state, ctx)
                self._mark(state, name, "done", payload=payload)
                self._save_state(cp_path, state)
            except Exception as e:
                self.log.exception(f"[ae-e2e] stage {name} failed")
                self._mark(state, name, "fail", payload={"error": str(e)})
                self._save_state(cp_path, state)
                if not ctx["dry_run"]:
                    # Fail-fast in non-dry-run mode mirrors the shell script's
                    # behaviour and keeps the operator's mental model simple.
                    return {
                        "run_id": state["run_id"],
                        "ok": False,
                        "failed_stage": name,
                        "error": str(e),
                        "checkpoint": str(cp_path),
                        "stages": state["stages"],
                    }
        return {
            "run_id": state["run_id"],
            "ok": True,
            "dry_run": ctx["dry_run"],
            "checkpoint": str(cp_path),
            "stages": state["stages"],
        }

    # ------------------------------------------------------------------
    # Stage 1 — preflight. Verifies caldera services / plugins reachable.
    # ------------------------------------------------------------------
    async def _stage_preflight(self, state: dict, ctx: dict) -> dict:
        services = self.services
        checks: list[dict] = []

        def chk(name: str, ok: bool, fail_hint: Optional[str] = None) -> None:
            entry = {"name": name, "ok": bool(ok)}
            if not ok and fail_hint:
                entry["extra"] = fail_hint
            checks.append(entry)

        chk("data_svc", services.get("data_svc") is not None)
        chk("file_svc", services.get("file_svc") is not None)
        chk("app_svc", services.get("app_svc") is not None)
        chk("rest_svc", services.get("rest_svc") is not None)
        chk("mcp_svc", services.get("mcp_svc") is not None)
        chk("range_svc", services.get("range_svc") is not None,
            fail_hint="OnPremService not registered; range plugin loaded?")
        chk("detection_svc", services.get("detection_svc") is not None,
            fail_hint="detections plugin not loaded; detections stage will skip")
        ok = all(c["ok"] for c in checks if c["name"] != "detection_svc")
        return {"ok": ok, "checks": checks, "dry_run": ctx["dry_run"]}

    # ------------------------------------------------------------------
    # Stage 2 — CTI ingest.
    # ------------------------------------------------------------------
    async def _stage_cti(self, state: dict, ctx: dict) -> dict:
        from plugins.mcp.app.cti_ingest_svc import CTIIngestService
        from plugins.mcp.app.utilities.paths import get_mcp_data_dir

        base_dir = get_mcp_data_dir()
        uploads = base_dir / "raw" / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)

        # Resolve & stage the CTI input file under data/raw/uploads/.
        if not ctx.get("cti_source"):
            raise RuntimeError("cti stage requires cti_source")
        src = Path(ctx["cti_source"])
        if not src.is_absolute():
            # Try a few likely roots so callers can pass repo-relative paths.
            for root in (Path.cwd(), base_dir.parent.parent.parent,
                         get_mcp_data_dir().parent):
                candidate = (root / src).resolve()
                if candidate.is_file():
                    src = candidate
                    break
        if not src.is_file():
            raise FileNotFoundError(f"cti_source not found: {ctx['cti_source']}")
        target = uploads / src.name
        if ctx["dry_run"]:
            self.log.info(f"[dry-run] would copy {src} -> {target}")
        else:
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)

        # Kick the pipeline. We do this off the event loop because the CTI
        # pipeline is CPU/network heavy (PDF parse, ATT&CK queries, LLM
        # extraction) and we don't want to block aiohttp's loop.
        if ctx["dry_run"]:
            self.log.info("[dry-run] would call CTIIngestService.run_stage(base_dir, 'all')")
        else:
            svc = CTIIngestService()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, svc.run_stage, base_dir, "all")

        # Look for outputs. The stage4 pipeline writes both:
        #   data/outputs_stix/<stem>.stix.json
        #   data/outputs_topology/<stem>.topology.json
        stem = src.stem
        outputs_stix = base_dir / "outputs_stix"
        outputs_topo = base_dir / "outputs_topology"

        def _match(p: Path) -> bool:
            s_norm = "".join(c for c in stem.lower() if c.isalnum())
            n_norm = "".join(c for c in p.stem.lower() if c.isalnum())
            return bool(s_norm) and s_norm in n_norm

        found_stix: Optional[Path] = None
        found_topo: Optional[Path] = None
        if not ctx["dry_run"]:
            # The pipeline ran synchronously above (run_in_executor). Files
            # should be present immediately, but allow a short grace window
            # for fs flush + slow filesystems.
            deadline = time.time() + 30
            while time.time() < deadline:
                if outputs_stix.is_dir():
                    for p in outputs_stix.glob("*.stix.json"):
                        if _match(p):
                            found_stix = p
                            break
                if outputs_topo.is_dir():
                    for p in outputs_topo.glob("*.topology.json"):
                        if _match(p):
                            found_topo = p
                            break
                if found_stix:
                    break
                await asyncio.sleep(2)

        counts: dict = {"malware": 0, "infrastructure": 0, "user_accounts": 0,
                        "hosts": 0, "identities": 0, "attack_patterns": 0,
                        "tools": 0, "relationships": 0}
        if found_stix:
            try:
                bundle = json.loads(found_stix.read_text(encoding="utf-8"))
                for o in bundle.get("objects", []):
                    t = o.get("type", "")
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
                    elif t == "x-cti-range-topology":
                        counts["hosts"] += len(o.get("hosts") or [])
            except Exception as e:
                self.log.warning(f"failed to count STIX objects: {e}")

        return {
            "input": str(src),
            "filename": src.name,
            "stix_path": str(found_stix) if found_stix else None,
            "topology_path": str(found_topo) if found_topo else None,
            "counts": counts,
            "dry_run": ctx["dry_run"],
        }

    # ------------------------------------------------------------------
    # Stage 3 — topology. Reuse the stage4 output when available, else
    # call build_range_topology in-process.
    # ------------------------------------------------------------------
    async def _stage_topology(self, state: dict, ctx: dict) -> dict:
        cti_payload = (state["stages"].get("cti") or {}).get("payload") or {}
        topo_path = cti_payload.get("topology_path")
        stix_path = cti_payload.get("stix_path")

        topo_obj: Optional[dict] = None
        if ctx["dry_run"]:
            topo_obj = {
                "type": "x-cti-range-topology",
                "id": "x-cti-range-topology--dry-run",
                "primary_platform": "windows",
                "hosts": [], "user_accounts": [], "identities": [],
            }
        elif topo_path and Path(topo_path).is_file():
            topo_obj = json.loads(Path(topo_path).read_text(encoding="utf-8"))
        elif stix_path and Path(stix_path).is_file():
            from plugins.mcp.app.utilities.cti_topology_inference import (
                build_range_topology,
            )
            taxonomy: dict = {}
            try:
                from plugins.mcp.app.utilities.cti_taxonomy_loader import (
                    load_mitre_taxonomy,
                )
                taxonomy = load_mitre_taxonomy() or {}
            except Exception as e:
                self.log.warning(f"taxonomy load failed: {e}; using empty taxonomy")
            images_catalog: list = []
            try:
                import yaml  # type: ignore
                ic_path = Path("plugins/range/conf/onprem_microvm_images.yml")
                if ic_path.is_file():
                    images_catalog = (yaml.safe_load(ic_path.read_text()) or {}).get("images") or []
            except Exception:
                pass
            bundle = json.loads(Path(stix_path).read_text(encoding="utf-8"))
            topo_obj = build_range_topology(bundle, taxonomy, images_catalog)
        else:
            raise RuntimeError("topology stage requires a stage_cti payload with stix_path or topology_path")

        # Persist for downstream stages + final report.
        out_path = Path("/tmp/e2e_full_vision_topology.json")
        out_path.write_text(json.dumps(topo_obj, indent=2, default=str), encoding="utf-8")
        return {
            "topology_id": topo_obj.get("id"),
            "primary_platform": topo_obj.get("primary_platform"),
            "host_count": len(topo_obj.get("hosts") or []),
            "user_count": len(topo_obj.get("user_accounts") or []),
            "identity_count": len(topo_obj.get("identities") or []),
            "saved_to": str(out_path),
            "dry_run": ctx["dry_run"],
        }

    # ------------------------------------------------------------------
    # Stage 4 — deploy_spec.
    # ------------------------------------------------------------------
    async def _stage_deploy_spec(self, state: dict, ctx: dict) -> dict:
        topo_path = Path("/tmp/e2e_full_vision_topology.json")
        if ctx["dry_run"]:
            spec = {
                "profile": ctx["profile_name"],
                "provider": "microvm",
                "images": [
                    {"image": "timestone-windows-victim", "name": "vm-dc-1",
                     "os": "Windows", "role": "dc", "cpus": 2, "memory": 2048,
                     "ansible_groups": ["tag_os_windows", "tag_role_dc"]},
                ],
                "elk_host": {"url": ctx["elk_url"], "kibana_url": ctx["kibana_url"]},
                "feature_playbooks": ["winlogbeat.yml"],
            }
        else:
            if not topo_path.is_file():
                raise FileNotFoundError("topology not built; run topology stage first")
            from plugins.mcp.app.utilities.cti_deploy_spec import synthesize_deploy_spec
            topo = json.loads(topo_path.read_text(encoding="utf-8"))
            ae_ir = None
            try:
                from plugins.mcp.app.utilities.cti_ae_library_loader import (
                    discover_ae_plans, find_plan_by_adversary, parse_ae_plan,
                )
                plans = discover_ae_plans()
                plan = find_plan_by_adversary(plans, ctx["adversary_slug"])
                if plan:
                    ae_ir = parse_ae_plan(plan, taxonomy=None)
            except Exception as e:
                self.log.warning(f"AE plan IR not loaded: {e}")
            images_catalog: list = []
            try:
                import yaml  # type: ignore
                ic_path = Path("plugins/range/conf/onprem_microvm_images.yml")
                if ic_path.is_file():
                    images_catalog = (yaml.safe_load(ic_path.read_text()) or {}).get("images") or []
            except Exception:
                pass
            spec = synthesize_deploy_spec(
                topo, ae_plan_ir=ae_ir, images_catalog=images_catalog,
                elk_host={"url": ctx["elk_url"], "kibana_url": ctx["kibana_url"]},
            )
            # Stamp our run's profile so deploys never collide.
            spec["profile"] = ctx["profile_name"]
            # The microvm provider is the only image set that boots in our env.
            spec["provider"] = "microvm"

        Path("/tmp/e2e_full_vision_deploy_spec.json").write_text(
            json.dumps(spec, indent=2, default=str), encoding="utf-8",
        )
        return {
            "profile": spec.get("profile"),
            "provider": spec.get("provider"),
            "image_count": len(spec.get("images") or []),
            "feature_playbooks": spec.get("feature_playbooks") or [],
            "elk_host": spec.get("elk_host"),
            "saved_to": "/tmp/e2e_full_vision_deploy_spec.json",
            "dry_run": ctx["dry_run"],
        }

    # ------------------------------------------------------------------
    # Stage 5 — deploy. In-process: build_onprem(profile, images).
    # ------------------------------------------------------------------
    async def _stage_deploy(self, state: dict, ctx: dict) -> dict:
        spec_path = Path("/tmp/e2e_full_vision_deploy_spec.json")
        spec: dict = {}
        if spec_path.is_file():
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        body = {
            "profile":  spec.get("profile") or ctx["profile_name"],
            "provider": spec.get("provider") or "microvm",
            "images":   spec.get("images") or [],
        }
        if ctx["dry_run"]:
            return {
                "profile": body["profile"], "provider": body["provider"],
                "image_count": len(body["images"]),
                "deploy_status": {"status": "running", "dry_run": True},
                "dry_run": True,
            }

        # Walk all registered services to find the OnPremService instance.
        # Multiple range objects (each cdktf provider, OnPremService itself)
        # all call `add_service("range_svc", self)` — the last writer wins,
        # which is typically a single provider like MicroVMProvider, NOT the
        # OnPremService that owns _deploy_status and build_onprem. So do not
        # trust `services["range_svc"]`; locate by capability instead.
        range_svc = None
        services_iter = self.services.values() if hasattr(self.services, "values") else []
        for svc in services_iter:
            if hasattr(svc, "_deploy_status") and hasattr(svc, "build_onprem"):
                range_svc = svc
                break
        if range_svc is None:
            # Fall back via the range plugin's GUI handler, which holds the
            # canonical onprem_svc reference on `self.onprem_svc`.
            try:
                for svc in services_iter:
                    onprem = getattr(svc, "onprem_svc", None)
                    if onprem is not None and hasattr(onprem, "_deploy_status"):
                        range_svc = onprem
                        break
            except Exception:
                pass
        if range_svc is None:
            raise RuntimeError(
                "OnPremService not found among registered services; "
                "range plugin must be loaded before the ae-e2e workflow runs."
            )

        # Resolve our stack_id the same way the GUI handler does so we can
        # watch _deploy_status[stack_id] directly without HTTP polling.
        from plugins.range.app.cdktf.cdktf_utilities import sanitize_stack_id
        stack_id = sanitize_stack_id(body["provider"], body["profile"])
        # Pre-mark deploying so the wait loop below never sees a stale 'idle'.
        range_svc._deploy_status[stack_id] = {"status": "deploying", "error": None}

        # Kick the deploy as a background task; we own the polling.
        async def _deploy_bg():
            try:
                await range_svc.build_onprem(profile=body["profile"], images=body["images"])
            except Exception as e:
                self.log.exception("build_onprem failed")
                range_svc._deploy_status[stack_id] = {"status": "error", "error": str(e)}

        deploy_task = asyncio.create_task(_deploy_bg())

        deadline = time.time() + ctx["deploy_timeout"]
        last_status: dict = {"status": "deploying", "error": None}
        while time.time() < deadline:
            raw = range_svc._deploy_status.get(stack_id) or {}
            last_status = {
                "status": raw.get("status", "unknown"),
                "error":  raw.get("error"),
                "last_phase": raw.get("last_phase"),
                "new_vm_names": raw.get("new_vm_names"),
            }
            self.log.info(f"[ae-e2e] deploy-status: {last_status['status']}")
            if last_status["status"] in ("running", "error", "idle"):
                break
            await asyncio.sleep(5)

        # If we timed out but the task hasn't finished, leave it running;
        # the next stage can decide whether to bail.
        if not deploy_task.done():
            self.log.warning("[ae-e2e] deploy poll loop ended while build_onprem still running")

        return {
            "profile": body["profile"],
            "provider": body["provider"],
            "image_count": len(body["images"]),
            "stack_id": stack_id,
            "deploy_status": last_status,
        }

    # ------------------------------------------------------------------
    # Stage 6 — meta. Scan TIMESTONE microvm runtime dir for live IPs.
    # ------------------------------------------------------------------
    async def _stage_meta(self, state: dict, ctx: dict) -> dict:
        base = Path(ctx["microvm_base"])
        hosts: list[dict] = []
        if ctx["dry_run"]:
            return {"hosts": [], "base": str(base), "dry_run": True}
        if not base.is_dir():
            return {"hosts": [], "base": str(base),
                    "warning": f"microvm runtime base {base} missing"}

        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            meta = d / "meta.json"
            if not meta.is_file():
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except Exception as e:
                self.log.warning(f"meta.json parse failed for {d}: {e}")
                continue
            hosts.append({
                "vm_name": data.get("vm_name") or d.name,
                "os": (data.get("os") or "").lower(),
                "ip": data.get("ip"),
                "cid": data.get("cid"),
                "tap": data.get("tap"),
                "run_dir": str(d),
                "vsock_uds": data.get("vsock_uds") or str(d / "shim.sock"),
                "serial": data.get("serial") or str(d / "serial.log"),
            })
        return {"base": str(base), "hosts": hosts}

    # ------------------------------------------------------------------
    # Stage 7 — sandcat. Subprocess ansible-playbook is acceptable.
    # ------------------------------------------------------------------
    async def _stage_sandcat(self, state: dict, ctx: dict) -> dict:
        meta_payload = (state["stages"].get("meta") or {}).get("payload") or {}
        hosts = meta_payload.get("hosts") or []
        if not hosts and not ctx["dry_run"]:
            return {"hosts": 0, "skipped": "no microvm hosts available"}

        inv_path = Path("/tmp/e2e_full_vision_inventory.ini")
        inv_path.write_text(_inventory_for(hosts), encoding="utf-8")

        plugin_range = Path("plugins/range")
        automation = plugin_range / "automation"
        microvm_implant = automation / "playbooks" / "microvm-implant.yml"
        winlogbeat = automation / "playbooks" / "feature" / "winlogbeat.yml"
        auditbeat = automation / "playbooks" / "feature" / "auditbeat.yml"

        primary = microvm_implant if microvm_implant.is_file() else None
        if not primary and not ctx["dry_run"]:
            return {"hosts": len(hosts), "skipped": "microvm-implant.yml not found"}

        caldera = caldera_connection()
        api_key = os.environ.get("CORE_CALDERA_API_KEY") or caldera["api_key"]
        caldera_url = os.environ.get("CALDERA_URL") or caldera["url"]
        for suffix in ("/api/v2/", "/api/v2"):
            if caldera_url.endswith(suffix):
                caldera_url = caldera_url[: -len(suffix)]
                break
        extra_vars = {
            "caldera_server": caldera_url,
            "caldera_apikey": api_key,
            "caldera_group": "red",
            "bridge_gateway": "192.168.66.1",
        }
        cmds: list[list[str]] = []
        if primary:
            cmds.append([
                "ansible-playbook", "-i", str(inv_path), str(primary),
                "--extra-vars", json.dumps(extra_vars),
            ])
        if winlogbeat.is_file() and any((h["os"] or "").lower() == "windows" for h in hosts):
            cmds.append([
                "ansible-playbook", "-i", str(inv_path), str(winlogbeat),
                "--extra-vars", json.dumps({"elk_host": ctx["elk_url"],
                                            "kibana_host": ctx["kibana_url"]}),
            ])
        if auditbeat.is_file() and any((h["os"] or "").lower() == "linux" for h in hosts):
            cmds.append([
                "ansible-playbook", "-i", str(inv_path), str(auditbeat),
                "--extra-vars", json.dumps({"elk_host": ctx["elk_url"],
                                            "kibana_host": ctx["kibana_url"]}),
            ])

        env = dict(os.environ)
        env["ANSIBLE_CONFIG"] = str(automation / "ansible.cfg")
        results: list[dict] = []
        loop = asyncio.get_running_loop()
        for cmd in cmds:
            if ctx["dry_run"]:
                results.append({"cmd": cmd, "rc": 0, "dry_run": True})
                continue
            try:
                r = await loop.run_in_executor(
                    None,
                    lambda c=cmd: subprocess.run(
                        c, env=env, cwd=str(automation),
                        capture_output=True, text=True, timeout=900,
                    ),
                )
                results.append({"cmd": cmd, "rc": r.returncode,
                                "stdout_tail": r.stdout[-2000:],
                                "stderr_tail": r.stderr[-2000:]})
            except Exception as e:
                results.append({"cmd": cmd, "error": str(e)})

        return {
            "inventory": str(inv_path),
            "primary_playbook": str(primary) if primary else None,
            "host_count": len(hosts),
            "runs": results,
            "dry_run": ctx["dry_run"],
        }

    # ------------------------------------------------------------------
    # Stage 8 — agents. Poll data_svc.locate('agents') in-process.
    # ------------------------------------------------------------------
    async def _stage_agents(self, state: dict, ctx: dict) -> dict:
        if ctx["dry_run"]:
            return {"paw_count": 0, "paws": [], "platforms": [], "dry_run": True}
        data_svc = self.services.get("data_svc")
        deadline = time.time() + ctx["agents_timeout"]
        agents: list = []
        while time.time() < deadline:
            agents = list(await data_svc.locate("agents")) or []
            if agents:
                break
            await asyncio.sleep(5)
        paws = [getattr(a, "paw", None) for a in agents]
        platforms = [getattr(a, "platform", None) for a in agents]
        return {
            "paw_count": len(paws),
            "paws": [p for p in paws if p],
            "platforms": [p for p in platforms if p],
        }

    # ------------------------------------------------------------------
    # Stage 9 — adversary. Build T-IDs from STIX bundle, locate abilities
    # in data_svc, build & store Adversary directly.
    # ------------------------------------------------------------------
    async def _stage_adversary(self, state: dict, ctx: dict) -> dict:
        from app.objects.c_adversary import Adversary

        if ctx["dry_run"]:
            return {"techniques": [], "ability_count": 0,
                    "adversary_id": "dry-run-adv", "dry_run": True}

        cti_payload = (state["stages"].get("cti") or {}).get("payload") or {}
        stix_path = cti_payload.get("stix_path")
        if not stix_path or not Path(stix_path).is_file():
            raise RuntimeError("adversary stage needs a stage_cti payload with stix_path")

        techniques: list[str] = []
        bundle = json.loads(Path(stix_path).read_text(encoding="utf-8"))
        for o in bundle.get("objects", []):
            if o.get("type") != "attack-pattern":
                continue
            for ref in o.get("external_references", []) or []:
                if (ref.get("source_name") or "").lower() != "mitre-attack":
                    continue
                eid = ref.get("external_id") or ""
                if eid.startswith("T"):
                    techniques.append(eid)
        techniques = sorted(set(techniques))

        agents_payload = (state["stages"].get("agents") or {}).get("payload") or {}
        platforms_seen = {(p or "").lower() for p in (agents_payload.get("platforms") or []) if p}
        if not platforms_seen:
            platforms_seen = {"windows", "linux"}

        data_svc = self.services.get("data_svc")
        all_abilities = list(await data_svc.locate("abilities")) or []

        chosen: list[str] = []
        for ab in all_abilities:
            tid = (getattr(ab, "technique_id", "") or "").strip()
            if not tid or tid not in techniques:
                continue
            ab_platforms: set[str] = set()
            for ex in getattr(ab, "executors", []) or []:
                p = (getattr(ex, "platform", "") or "").lower()
                if p:
                    ab_platforms.add(p)
            if ab_platforms and not (ab_platforms & platforms_seen):
                continue
            ability_id = getattr(ab, "ability_id", None)
            if ability_id:
                chosen.append(ability_id)
        chosen = list(dict.fromkeys(chosen))

        adv_name = f"E2E AE-Pipeline {_iso()}"
        adv = Adversary(
            name=adv_name,
            description=f"Auto-built from CTI ingest ({ctx['adversary_slug']})",
            atomic_ordering=chosen,
            tags=["e2e-full-vision", "ae-e2e"],
        )
        await data_svc.store(adv)
        return {
            "techniques": techniques,
            "ability_count": len(chosen),
            "adversary_id": adv.adversary_id,
            "adversary_name": adv_name,
        }

    # ------------------------------------------------------------------
    # Stage 10 — operation. Build + run via the v2 operation manager.
    # ------------------------------------------------------------------
    async def _stage_operation(self, state: dict, ctx: dict) -> dict:
        if ctx["dry_run"]:
            return {"operation_id": "dry-run-op", "final_state": "finished",
                    "dry_run": True}

        adv = (state["stages"].get("adversary") or {}).get("payload") or {}
        adv_id = adv.get("adversary_id")
        if not adv_id:
            raise RuntimeError("operation stage requires adversary_id from stage_adversary")

        # Use the v2 OperationApiManager since that's the canonical code
        # path for v2 REST. Same input shape, same task scheduling.
        from app.api.v2.managers.operation_api_manager import OperationApiManager
        from app.objects.c_operation import Operation, OperationSchema
        from app.utility.base_world import BaseWorld

        mgr = OperationApiManager(self.services)
        op_data = {
            "name": f"e2e-ae-{int(time.time())}",
            "adversary": {"adversary_id": adv_id},
            "group": "red",
            "planner": {"id": "atomic"},
            "source": {"id": "basic"},
            "state": "running",
            "autonomous": 1,
        }
        access = {"access": (BaseWorld.Access.RED,)}
        operation = await mgr.create_object_from_schema(
            OperationSchema, op_data, BaseWorld.Access.RED,
        )

        op_id = getattr(operation, "id", None)
        deadline = time.time() + ctx["operation_timeout"]
        final_state = None
        data_svc = self.services.get("data_svc")
        while time.time() < deadline and op_id:
            ops = await data_svc.locate("operations", match=dict(id=op_id))
            if ops:
                cur = ops[0]
                st = getattr(cur, "state", "") or ""
                if hasattr(st, "value"):
                    st = st.value
                self.log.info(f"[ae-e2e] op {op_id} state={st}")
                if st in ("finished", "cleanup", "completed"):
                    final_state = st
                    break
            await asyncio.sleep(10)

        return {
            "operation_id": op_id,
            "final_state": final_state,
        }

    # ------------------------------------------------------------------
    # Stage 11 — detections. Call DetectionService.validate_operation
    # directly.
    # ------------------------------------------------------------------
    async def _stage_detections(self, state: dict, ctx: dict) -> dict:
        if ctx["dry_run"]:
            return {"per_link": [], "dry_run": True}

        op = (state["stages"].get("operation") or {}).get("payload") or {}
        op_id = op.get("operation_id")
        if not op_id:
            return {"skipped": "no operation_id"}

        detection_svc = self.services.get("detection_svc")
        if detection_svc is None:
            return {"skipped": "detection_svc not loaded"}

        try:
            results = await detection_svc.validate_operation(op_id) or []
        except Exception as e:
            return {"error": f"validate_operation failed: {e}"}

        summary: dict = {"per_link": [], "coverage_scores": []}
        for r in results:
            # DetectionResult is a dataclass-like object in the detections
            # plugin; fall back to attribute lookup with defaults so we
            # don't crash if the shape evolves.
            entry = {
                "link_id": getattr(r, "link_id", None),
                "ability_logs": len(getattr(r, "ability_logs", []) or []),
                "matching_rules": len(getattr(r, "matching_rules", []) or []),
                "rules_that_would_fire": len(getattr(r, "rules_that_would_fire", []) or []),
                "coverage_score": getattr(r, "coverage_score", None),
            }
            summary["per_link"].append(entry)
            if entry["coverage_score"] is not None:
                summary["coverage_scores"].append(entry["coverage_score"])
        if summary["coverage_scores"]:
            summary["mean_coverage"] = round(
                sum(summary["coverage_scores"]) / len(summary["coverage_scores"]), 3,
            )
        return summary

    # ------------------------------------------------------------------
    # Stage 12 — report.
    # ------------------------------------------------------------------
    async def _stage_report(self, state: dict, ctx: dict) -> dict:
        lines: list[str] = []
        lines.append(f"# ae-e2e run report — {_iso()}")
        lines.append("")
        lines.append(f"run_id: `{state.get('run_id')}`  ")
        lines.append(f"started: `{state.get('started')}`  ")
        lines.append(f"updated: `{state.get('updated')}`  ")
        lines.append("")
        for name in STAGES:
            rec = state["stages"].get(name) or {}
            status = rec.get("status", "skip")
            lines.append(f"## stage `{name}` — {status}")
            for k, v in rec.items():
                if k == "payload":
                    continue
                lines.append(f"- {k}: `{v}`")
            if "payload" in rec:
                try:
                    blob = json.dumps(rec["payload"], indent=2, default=str)[:4000]
                    lines.append("")
                    lines.append("```json")
                    lines.append(blob)
                    lines.append("```")
                except Exception as e:
                    lines.append(f"_payload-render-failed: {e}_")
            lines.append("")
        _DEFAULT_REPORT.write_text("\n".join(lines), encoding="utf-8")
        return {"report_path": str(_DEFAULT_REPORT), "dry_run": ctx["dry_run"]}


# ----------------------------------------------------------------------
# Inventory helper. Lifted verbatim from scripts/e2e_full_vision_lib.py
# so the inventory the workflow generates matches what the timestone
# connection plugin expects.
# ----------------------------------------------------------------------
def _inventory_for(hosts: list[dict]) -> str:
    out: list[str] = []
    out.append("# generated by plugins/mcp/app/workflows/ae_e2e.py")
    out.append("")

    def host_line(h: dict) -> str:
        name = h["vm_name"]
        ip = h.get("ip") or "0.0.0.0"
        os_kind = (h.get("os") or "linux").lower()
        vars_ = [
            f"ansible_host={ip}",
            "ansible_connection=timestone_microvm",
            f"timestone_os={os_kind}",
            f"timestone_run_dir={h.get('run_dir', '')}",
        ]
        if os_kind == "linux":
            vars_.append(f"timestone_vsock_uds={h.get('vsock_uds', '')}")
        else:
            vars_.append(f"timestone_serial={h.get('serial', '')}")
        return f"{name} " + " ".join(vars_)

    linux = [h for h in hosts if (h.get("os") or "").lower() == "linux"]
    windows = [h for h in hosts if (h.get("os") or "").lower() == "windows"]

    out.append("[tag_os_linux]")
    out += [host_line(h) for h in linux]
    out.append("")
    out.append("[tag_os_windows]")
    out += [host_line(h) for h in windows]
    out.append("")
    out.append("[microvms_linux:children]")
    out.append("tag_os_linux")
    out.append("")
    out.append("[microvms_windows:children]")
    out.append("tag_os_windows")
    out.append("")
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------
# Workflow registration. The Workflow dataclass expects ``run`` to be an
# awaitable; the ae-e2e workflow is not an LLM workflow so it doesn't
# need a real DSPy signature, but Workflow demands one. We use a stub
# that's never instantiated.
# ----------------------------------------------------------------------
import dspy  # noqa: E402


class _AeE2EStubSignature(dspy.Signature):
    """Stub signature for the ae-e2e workflow.

    Not exercised at request time — the API endpoint bypasses the
    DSPy/LM machinery and calls AEEndToEndWorkflow.run() directly. The
    signature is here only because Workflow.signature is non-optional.
    """
    adversary_emulation_task: str = dspy.InputField(default="")
    process_result: str = dspy.OutputField()


async def _workflow_runner(prompt: str = "", lm_obj=None, *, run_id=None,
                            enabled_servers=None, server_registry=None,
                            services=None, **kwargs) -> dict:
    """Adapter so the plain Workflow.run signature works.

    Two callers can hit this:
      1. The new POST /plugin/mcp/workflows/run-ae-end-to-end endpoint,
         which passes ``services`` explicitly + structured kwargs.
      2. The generic /plugin/mcp/execute path, which feeds prompt + lm_obj
         (we just ignore them — the ae-e2e workflow has no LLM step).
    """
    if services is None:
        raise RuntimeError(
            "ae-e2e workflow requires the caldera services dict; "
            "call POST /plugin/mcp/workflows/run-ae-end-to-end instead "
            "of /plugin/mcp/execute"
        )
    wf = AEEndToEndWorkflow(services)
    result = await wf.run(**kwargs)
    # Conform to the {process_result: str} shape so /execute callers still
    # get something useful in the UI.
    return {
        "process_result": json.dumps(result, indent=2, default=str)[:8000],
        "ae_e2e": result,
    }


# Intentionally no top-level Workflow registration: ae-e2e is invoked
# either by the `cti_pipeline` MCP tools (which plan_execute's LLM
# selects when the user asks for the end-to-end run) or by the
# scripts/e2e_full_vision.sh CLI client. Exposing it as a separate
# workflow card duplicated plan_execute's role and confused the UX.
# The AEEndToEndWorkflow class + POST /plugin/mcp/workflows/run-ae-end-to-end
# endpoint remain available for those programmatic callers.
WORKFLOWS = []
