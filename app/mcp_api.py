from aiohttp import web
import logging
import re
import mlflow
import os
import json
import yaml
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from app.service.auth_svc import for_all_public_methods, check_authorization

from plugins.mcp.app.config import llm_defaults
from plugins.mcp.app.utilities.llm_client import (
    LLM_OVERRIDABLE,
    LLM_PROFILES,
    WORKLOAD_OVERRIDABLE,
    deep_merge,
    layered_profile,
    load_config,
    reload_config,
    resolve_env_indirection,
    unwrap_config_envelope,
)
from plugins.mcp.app.utilities.cti_raw_cleaner import clean_stem
from plugins.mcp.app.utilities.paths import get_mcp_data_dir, get_mcp_root
from plugins.mcp.app.cti_ingest_svc import CTIIngestService

# Fallbacks for UI fields the yaml doesn't model. The numeric LM tunables
# come back from llm_defaults() which already applies its own fallbacks;
# the RAG-specific defaults stay here because they belong to the capability
# rather than the LLM provider.
#
# rag_embed_model has no literal default: an undeclared embedding model falls
# back to the configured chat model, since a deployment pointing at its own
# gateway has no reason to reach for an OpenAI model name it never chose.
_RAG_DEFAULTS = {
    "rag_topk": 5,
}

# conf/local.yml is plaintext on disk beside tracked config, so credentials
# never go in it. They come from .env or the per-session UI.
# Matched by name rather than listed: the UI keeps growing key fields
# (embed_api_key, plan_api_key, cti_rag_api_key) and a list keeps missing them.
# api_key_env names a variable, not a value, so it is kept.
# Widened past api_key: a gateway credential also arrives as an Authorization
# or x-api-key header, and the llm section used to accept any key at all, so
# all three reached the file in plaintext.
# max_tokens contains "token" and is a generation setting, not a credential,
# so the token alternative excludes it explicitly. Dropping it silently is
# worse than not matching a credential, because the operator sees a saved
# value vanish with no error.
_SECRET_KEY_NAME = re.compile(
    r"(api[-_]?key|authorization|bearer|(?<!max_)token"
    r"|secret|password|passwd|credential)",
    re.IGNORECASE,
)

# The only top-level sections conf/local.yml has meaning for. An unknown one
# is either a typo or an attempt to write something nothing reads.
_KNOWN_SECTIONS = LLM_PROFILES | {"caldera", "mlflow"}

# The non-LLM sections, which the profile allowlists do not cover.
_SECTION_OVERRIDABLE = {
    "mlflow": frozenset({"host", "port"}),
    "caldera": frozenset({"url_env", "api_key_env"}),
}

# hook.py passes mlflow.host straight to "mlflow server --host", and that
# server holds every prompt and response the plugin has logged, unauthenticated.
# Rebinding it off loopback is a deployment decision, not a UI one.
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Mirrors the dispatch in llm_client.LLMClient.generate.
_VALID_PROVIDERS = {"openai_compatible", "ollama"}


def _stop_reason(tags) -> str:
    """Why a KILLED run stopped: "user", "orphaned", or "" for anything else."""
    if tags.get("mcp.cancelled") == "user":
        return "user"
    if tags.get("mcp.reconciled") == "orphaned":
        return "orphaned"
    return ""


def _is_secret(name) -> bool:
    return bool(_SECRET_KEY_NAME.search(str(name))) and not str(name).endswith("_env")


def _without_secrets(value):
    """Recursive: callers have posted nested shapes, so one level is not enough."""
    if isinstance(value, dict):
        return {k: _without_secrets(v) for k, v in value.items() if not _is_secret(k)}
    if isinstance(value, list):
        return [_without_secrets(v) for v in value]
    return value

# Caldera gates plugin routes per handler, not with a middleware: auth_svc.apply
# only installs the session and security machinery, and check_authorization is
# what calls check_permissions. Without this every route here was reachable
# unauthenticated, including the ones that delete files and rewrite local.yml.
# McpGUI in this same plugin already carries it, as do access, gameboard and
# human. Every public method on this class is a registered route.
@for_all_public_methods(check_authorization)
class McpAPI:

    def __init__(self, services):
        self.services = services
        # check_authorization reaches for self.auth_svc on the instance.
        self.auth_svc = services.get("auth_svc")
        # Outcome of the most recent CTI run. cti_run returns as soon as the
        # work is scheduled, so this is the only thing the browser can poll to
        # learn that a run failed.
        self._cti_run = {"state": "idle", "step": None, "files": [], "error": None}
        self.mcp_svc = services.get("mcp_svc")
        self.log = logging.getLogger("plugins.mcp")
        self.log.info("[MCP] Initialized McpAPI")
        # CTI ingestion endpoints (merged from CTI branch) need a stable
        # data dir and plugin root to read/write STIX bundles and raw
        # uploads. Resolve once here so each handler can reference
        # self.base_dir / self.root_dir without recomputing.
        self.base_dir = get_mcp_data_dir()
        self.root_dir = get_mcp_root()

    def _mcp_server_catalog(self):
        registry = getattr(self.mcp_svc, "server_registry", None) or {}
        servers = []
        for name, info in registry.items():
            metadata = dict(info.get("metadata") or {})
            servers.append({
                "name": name,
                "display_name": metadata.get("display_name", name),
                "default_enabled": bool(metadata.get("default_enabled", False)),
                "description": metadata.get("description", ""),
            })
        servers.sort(key=lambda s: (not s["default_enabled"], s["name"]))
        return servers

    def _mcp_workflow_catalog(self):
        wf_registry = getattr(self.mcp_svc, "workflow_registry", None) or {}
        srv_registry = getattr(self.mcp_svc, "server_registry", None) or {}
        available_servers = set(srv_registry.keys())

        workflows = []
        for wf in wf_registry.values():
            missing = [s for s in wf.required_servers if s not in available_servers]
            if missing:
                self.log.info(
                    f"[MCP] Hiding workflow '{wf.id}'; missing required servers: {missing}"
                )
                continue
            workflows.append({
                "id": wf.id,
                "display_name": wf.display_name,
                "description": wf.description,
                "required_servers": list(wf.required_servers),
                "optional_servers": [
                    s for s in wf.optional_servers if s in available_servers
                ],
                "accepted_capabilities": list(wf.accepted_capabilities),
                "ui_component": wf.ui_component,
                "example_prompts": list(wf.example_prompts),
                "plan_validator": wf.plan_validator,
                "supports_chat_history": bool(getattr(wf, "supports_chat_history", False)),
            })
        workflows.sort(key=lambda w: w["display_name"].lower())
        return workflows

    def _mcp_capability_catalog(self):
        cap_registry = getattr(self.mcp_svc, "capability_registry", None) or {}
        capabilities = []
        for cap in cap_registry.values():
            capabilities.append({
                "id": cap.id,
                "display_name": cap.display_name,
                "description": cap.description,
                "ui_settings_component": cap.ui_settings_component,
                "contributes_fields": list(cap.contributes_fields),
            })
        capabilities.sort(key=lambda c: c["display_name"].lower())
        return capabilities

    def _registered_service(self, name):
        try:
            return self.services.get(name)
        except Exception:
            return None
    async def execute(self, request):
        """POST /plugin/mcp/execute.

        New payload shape (preferred):
            {
              "text": "...",
              "workflow_id": "author" | "plan_execute" | ...,
              "lm_config": { model, api_key, api_base, temperature, max_tokens, max_tool_calls },
              "enabled_servers": ["caldera_core", ...],
              "enabled_capabilities": ["rag", ...],
              "capability_settings": { "rag": { "rag_files": [...], "topk": 5, "embed_model": "..." } },
              "workflow_context": { ...workflow-specific UI/runtime options... }
            }

        Legacy payload (still accepted, mapped by mcp_svc):
            { "text": "...", "type": "factory"|"planner"|"rag_factory"|"rag_planner",
              "config": { ...lm + rag_files/rag_topk/rag_embed_model }, "enabled_servers": [...] }
        """
        self.log.info("[MCP] Executing request")
        try:
            data = await request.json()
            user_input = data.get("text", "")
            if not user_input:
                return web.json_response({"error": 'Missing "text" in request'}, status=400)

            workflow_id = data.get("workflow_id")
            lm_config = data.get("lm_config")
            enabled_capabilities = data.get("enabled_capabilities")
            capability_settings = data.get("capability_settings")
            enabled_servers = data.get("enabled_servers")
            workflow_context = data.get("workflow_context") or {}
            # Optional. Absent on the first turn of a chat; the response
            # echoes back the assigned session_id so the client can pass it
            # on follow-up turns. Workflows that opt out of chat history
            # ignore this value entirely.
            session_id = data.get("session_id")
            # Per-request override letting the user disable chat history
            # mid-session even when the workflow opts in. The flag gates
            # both reading prior turns into this prompt and recording the
            # new turn afterwards, so a history-off prompt is a clean
            # side conversation that does not affect the session thread.
            disable_history = bool(data.get("disable_history", False))

            # Legacy fields (only used when workflow_id is absent)
            focus = data.get("type")
            model_config = data.get("config")

            self.log.info(
                f"[MCP] workflow_id={workflow_id} legacy_type={focus} "
                f"session_id={session_id} "
                f"enabled_servers={enabled_servers} "
                f"enabled_capabilities={enabled_capabilities} "
                f"workflow_context_keys={list(workflow_context) if isinstance(workflow_context, dict) else []}"
            )

            result = await self.mcp_svc.execute(
                workflow_id=workflow_id,
                focus=focus,
                prompt=user_input,
                lm_config=lm_config,
                model_config=model_config,
                enabled_servers=enabled_servers,
                enabled_capabilities=enabled_capabilities,
                capability_settings=capability_settings,
                workflow_context=workflow_context,
                session_id=session_id,
                disable_history=disable_history,
            )
            return web.json_response(result)

        except Exception as e:
            self.log.error(f"[MCP] Error executing request: {str(e)}")
            return web.json_response({"error": str(e)}, status=500)

    async def defaults(self, request):
        """Resolved defaults for the Global Model Config UI panel.

        api_key is always returned as empty string so the server-side
        credential never reaches the browser; the UI prompts the user to
        enter their own (or leave blank to fall back to the .env value at
        request time).

        fields_locked tells the UI which inputs the deployment fixes (e.g.
        a gateway with a constrained model list); the UI greys those out
        and the resolver also drops any UI overrides for them.
        """
        try:
            cfg = llm_defaults()
            payload = {
                "model": cfg.get("model"),
                "api_key": "",
                "api_base": cfg.get("api_base"),
                "temperature": cfg.get("temperature"),
                "max_tokens": cfg.get("max_tokens"),
                "max_tool_calls": cfg.get("max_tool_calls"),
                "timeout": cfg.get("timeout"),
                "ssl_verify": cfg.get("ssl_verify", True),
                "fields_locked": cfg.get("fields_locked") or {},
            }
            for key, fallback in _RAG_DEFAULTS.items():
                payload[key] = cfg.get(key, fallback)
            payload["rag_embed_model"] = (
                cfg.get("rag_embed_model")
                or cfg.get("embed_model")
                or cfg.get("model")
            )
            return web.json_response(payload)
        except Exception as e:
            self.log.error(f"[MCP] Error fetching defaults: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_servers(self, request):
        """Return discovered MCP server registry for UI toggles."""
        try:
            return web.json_response({"servers": self._mcp_server_catalog()})
        except Exception as e:
            self.log.error(f"[MCP] Error listing servers: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_workflows(self, request):
        """Return discovered Workflow registry so the UI can render cards.

        Workflows whose required servers are not all present in the discovered
        server registry are filtered out, since they cannot run anyway.
        """
        try:
            return web.json_response({"workflows": self._mcp_workflow_catalog()})
        except Exception as e:
            self.log.error(f"[MCP] Error listing workflows: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_capabilities(self, request):
        """Return discovered Capability registry so the UI can render settings panels."""
        try:
            return web.json_response({"capabilities": self._mcp_capability_catalog()})
        except Exception as e:
            self.log.error(f"[MCP] Error listing capabilities: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def features(self, request):
        """Return the MCP-facing feature catalog in one API call."""
        try:
            return web.json_response({
                "mcp": {
                    "servers": self._mcp_server_catalog(),
                    "workflows": self._mcp_workflow_catalog(),
                    "capabilities": self._mcp_capability_catalog(),
                    "endpoints": {
                        "servers": "/plugin/mcp/servers",
                        "workflows": "/plugin/mcp/workflows",
                        "capabilities": "/plugin/mcp/capabilities",
                    },
                },
            })
        except Exception as e:
            self.log.error(f"[MCP] Error listing feature catalog: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def cancel(self, request):
        """POST /plugin/mcp/cancel {"run_id": ...}. Stop one in-flight run.

        Always answers 200 for a well-formed body: pressing Stop twice, or
        after the run already finished, is a no-op reported as
        cancelling=false. The caller keeps polling /status to see the run
        reach KILLED, which takes as long as the workflow needs to unwind.
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Body must be JSON"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "Body must be a JSON object"}, status=400)

        run_id = data.get("run_id")
        # Typed, not just present: run_id is used as a dict key, and an
        # unhashable one would answer a bad request with a 500.
        if not run_id or not isinstance(run_id, str):
            return web.json_response({"error": "Missing run_id"}, status=400)

        cancelling = self.mcp_svc.cancel_run(run_id)
        snapshot = self.mcp_svc.get_run(run_id) or {}
        return web.json_response({
            "run_id": run_id,
            "cancelling": cancelling,
            "status": snapshot.get("status", "UNKNOWN"),
        })

    async def status(self, request):
        """Live status of an in-flight or recently-finished run.

        Reads from the in-memory cache on MCPService rather than from
        MLflow. The cache is the single source of truth for live state
        and carries exactly what the agent loop returned. MLflow stays
        as the observability backbone and the data source for the
        History tab (see list_runs / get_run_detail below).

        Returns 404 when the run_id is unknown to the cache (typically
        means the server restarted, or the run is older than the LRU
        bound). The History endpoints can still surface those runs.
        """
        run_id = request.query.get("run_id")
        if not run_id:
            return web.json_response({"error": "Missing run_id"}, status=400)

        snapshot = self.mcp_svc.get_run(run_id)
        if snapshot is None:
            return web.json_response(
                {"run_id": run_id, "status": "UNKNOWN",
                 "error": "run not in live cache; try /history/run for older runs"},
                status=404,
            )

        # The chat UI polls this endpoint roughly every second while a run
        # is in flight; INFO would print hundreds of lines per long run for
        # the expected happy path. Drop to DEBUG so operators can still
        # opt in via log level when troubleshooting.
        self.log.debug(f"[MCP] Status for run {run_id} served from cache")
        return web.json_response({"run_id": run_id, **snapshot})

    async def upload_rag(self, request):
        try:
            reader = await request.multipart()
            part = await reader.next()
            if not part or part.name != "file":
                return web.json_response({"error": 'Missing "file" field in form-data'}, status=400)

            raw_filename = part.filename or "rag.json"
            filename = os.path.basename(raw_filename)

            if not filename.lower().endswith(".json"):
                return web.json_response({"error": "Only .json files are allowed"}, status=400)

            base_dir = (Path(__file__).resolve().parent.parent / "data")
            base_dir.mkdir(parents=True, exist_ok=True)

            target_path = base_dir / filename
            if target_path.exists():
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                filename = f"{stem}_{ts}{suffix}"
                target_path = base_dir / filename

            file_bytes = await part.read()
            try:
                _ = json.loads(file_bytes.decode("utf-8"))
            except Exception as e:
                return web.json_response({"error": f"Invalid JSON: {e}"}, status=400)

            with open(target_path, "wb") as f:
                f.write(file_bytes)

            stat = target_path.stat()
            self.log.info(f"[MCP] Uploaded RAG file to {target_path} ({stat.st_size} bytes)")
            return web.json_response({
                "message": "RAG file uploaded",
                "filename": filename,
                "size": stat.st_size,
                "path": str(target_path)
            })
        except Exception as e:
            self.log.error(f"[MCP] Error uploading RAG file: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_rag(self, request):
        try:
            base_dir = (Path(__file__).resolve().parent.parent / "data")
            files = []
            if base_dir.exists():
                for p in base_dir.glob("*.json"):
                    try:
                        stat = p.stat()
                        files.append({
                            "filename": p.name,
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
                        })
                    except Exception:
                        continue
            return web.json_response({"files": sorted(files, key=lambda x: x["filename"].lower())})
        except Exception as e:
            self.log.error(f"[MCP] Error listing RAG files: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_runs(self, request):
        """List all MLflow runs with basic information."""
        try:
            # Get optional query parameters for filtering/pagination
            limit = int(request.query.get("limit", 100))
            offset = int(request.query.get("offset", 0))

            client = mlflow.tracking.MlflowClient()

            # Get all experiments (in case there are multiple)
            experiments = client.search_experiments()

            all_runs = []
            for experiment in experiments:
                # Search runs in this experiment
                runs = client.search_runs(
                    experiment_ids=[experiment.experiment_id],
                    order_by=["start_time DESC"],
                    max_results=1000  # Get a large number, we'll paginate ourselves
                )

                for run in runs:
                    run_info = run.info
                    run_data = run.data

                    # Extract key information
                    run_record = {
                        "run_id": run_info.run_id,
                        "experiment_id": run_info.experiment_id,
                        "status": run_info.status,
                        "start_time": run_info.start_time,
                        "end_time": run_info.end_time,
                        "run_name": run_data.tags.get("mlflow.runName", "Unnamed Run"),
                        "prompt": run_data.params.get("prompt", ""),
                        "stage": run_data.tags.get("stage", ""),
                        "model": run_data.params.get("model", ""),
                        # The result is written as a tag, never as a param,
                        # so params.process_result was always empty.
                        "process_result": (
                            run_data.tags.get("process_result_summary")
                            or run_data.tags.get("process_result", "")
                        ),
                        # Both a user stop and the boot sweep land on KILLED;
                        # only the tags say which, and they read differently.
                        "stop_reason": _stop_reason(run_data.tags),
                    }
                    all_runs.append(run_record)

            # Sort by start_time descending (newest first)
            all_runs.sort(key=lambda x: x["start_time"], reverse=True)

            # Apply pagination
            paginated_runs = all_runs[offset:offset + limit]

            return web.json_response({
                "runs": paginated_runs,
                "total": len(all_runs),
                "limit": limit,
                "offset": offset
            })
        except Exception as e:
            self.log.error(f"[MCP] Error listing runs: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def get_run_detail(self, request):
        """Get detailed information for a specific run including full trajectory."""
        run_id = request.query.get("run_id")
        if not run_id:
            return web.json_response({"error": "Missing run_id"}, status=400)

        try:
            client = mlflow.tracking.MlflowClient()
            run = client.get_run(run_id)

            # Extract all trajectory data (thoughts, observations, tool calls)
            trajectory = {
                k: v for k, v in run.data.tags.items()
                if k.startswith("thought_") or k.startswith("observation_") or
                   k.startswith("tool_name_") or k.startswith("tool_args_")
            }

            # Build comprehensive response
            response = {
                "run_id": run_id,
                "status": run.info.status,
                "stop_reason": _stop_reason(run.data.tags),
                "start_time": run.info.start_time,
                "end_time": run.info.end_time,
                "run_name": run.data.tags.get("mlflow.runName", "Unnamed Run"),
                "experiment_id": run.info.experiment_id,
                "params": dict(run.data.params),
                "tags": dict(run.data.tags),
                "trajectory": trajectory,
                "stage": run.data.tags.get("stage"),
                "reasoning": run.data.tags.get("reasoning"),
                "prompt": run.data.params.get("prompt"),
                # Workflows tag the full result and log it as the
                # result_summary param; params.process_result never exists,
                # so the detail view's Result box never rendered.
                "process_result": (
                    run.data.tags.get("process_result")
                    or run.data.params.get("result_summary", "")
                ),
            }

            return web.json_response(response)
        except Exception as e:
            self.log.error(f"[MCP] Error fetching run detail {run_id}: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # ===== CTI ingestion endpoints (imported from CTI branch) =====

    # CTI vue
    async def cti_run(self, request):
        try:
            try:
                data = await request.json()
            except Exception:
                return web.json_response(
                    {"error": "Body must be JSON"}, status=400
                )
            if not isinstance(data, dict):
                return web.json_response(
                    {"error": "Body must be a JSON object"}, status=400
                )

            files = data.get("files")
            step = data.get("step", "all")

            if not files or not isinstance(files, list):
                return web.json_response(
                    {"error": "Missing files list"},
                    status=400
                )
            # Every name is joined onto a Path below, so a non-string element
            # raises TypeError and surfaces as a 500. The upload handlers pass
            # their filenames through basename; this one never did, so a name
            # with a separator escaped the uploads directory.
            if not all(isinstance(f, str) and f.strip() for f in files):
                return web.json_response(
                    {"error": "files must be a list of non-empty strings"},
                    status=400
                )
            if any(f != os.path.basename(f) for f in files):
                return web.json_response(
                    {"error": "files must be bare filenames"},
                    status=400
                )

            uploads = self.base_dir / "raw" / "uploads"
            processed = self.base_dir / "raw" / "processed"

            uploads.mkdir(parents=True, exist_ok=True)
            processed.mkdir(parents=True, exist_ok=True)

            # 1️⃣ Rehydrate selected items (for re-runs)
            # The selection has to reach the service: clean/ accumulates, so
            # without it Stage 1 re-extracts every report ever ingested while
            # the browser reports the count the operator picked.
            svc = CTIIngestService(selected=files)

            uploads_dir = self.base_dir / "raw" / "uploads"
            processed_dir = self.base_dir / "raw" / "processed"

            # Only rehydrate files that are NOT already pending
            to_rehydrate = []

            for name in files:
                if not (uploads_dir / name).exists() and (processed_dir / name).exists():
                    to_rehydrate.append(name)

            if to_rehydrate:
                svc.prepare_uploads(self.base_dir, to_rehydrate)

            # 2️⃣ Run pipeline (NON-BLOCKING)
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                None,
                svc.run_stage,
                self.base_dir,
                step
            )

            self._cti_run = {
                "state": "running", "step": step, "files": files, "error": None,
            }

            # run_stage re-raises after marking FAILED. Without retrieving the
            # result the exception dies with the future, so a run that failed
            # immediately looked identical to one still working: no log line,
            # and the file stuck on "pending" forever. The outcome is recorded
            # here too, because the service instance is local to this request
            # and the browser has nothing else to poll.
            def _report(fut):
                exc = fut.exception()
                if exc is None:
                    self._cti_run = {
                        "state": "complete", "step": step, "files": files,
                        "error": None,
                    }
                    self.log.info(f"[MCP] CTI pipeline finished: step={step}")
                else:
                    self._cti_run = {
                        "state": "failed", "step": step, "files": files,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    self.log.error(
                        f"[MCP] CTI pipeline failed: step={step} files={files}",
                        exc_info=exc,
                    )

            future.add_done_callback(_report)
            self.log.info(f"[MCP] CTI pipeline started: step={step} files={files}")

            return web.json_response({
                "status": "started",
                "files": files,
                "step": step
            })

        except Exception as e:
            self.log.error(f"[MCP] CTI run failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def upload_stix_cti(self, request):
        try:
            reader = await request.multipart()
            part = await reader.next()
            if not part or part.name != "file":
                return web.json_response({"error": 'Missing "file" field in form-data'}, status=400)

            raw_filename = part.filename or "cti.stix.json"
            filename = os.path.basename(raw_filename)

            if not filename.lower().endswith(".json"):
                return web.json_response({"error": "Only .json files are allowed"}, status=400)

            self.base_dir.mkdir(parents=True, exist_ok=True)

            # Same directory the four read handlers and the pipeline use.
            # Uploading to stix_cti made every bundle invisible to list,
            # get, download and delete.
            rag_dir = self.base_dir / "outputs_stix"
            rag_dir.mkdir(parents=True, exist_ok=True)
            target_path = rag_dir / filename
            if target_path.exists():
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                target_path = rag_dir / f"{target_path.stem}_{ts}.json"

            data = await part.read()
            json.loads(data.decode("utf-8"))  # validate JSON

            target_path.write_bytes(data)

            self.log.info(f"[MCP] CTI STIX uploaded: {target_path}")

            return web.json_response({
                "message": "CTI STIX uploaded",
                "filename": target_path.name
            })

        except Exception as e:
            self.log.error(f"[MCP] STIX upload failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_stix_cti(self, request):
        try:
            stix_dir = self.base_dir / "outputs_stix"

            files = []

            if stix_dir.exists():
                for p in stix_dir.glob("*.json"):
                    stat = p.stat()

                    model = None
                    provider = None
                    extractor = None

                    try:
                        with p.open("r", encoding="utf-8") as f:
                            bundle = json.load(f)
                            model = bundle.get("x_cti_model")
                            provider = bundle.get("x_cti_provider")
                            extractor = (bundle.get("x_cti_config") or {}).get("extractor")
                    except Exception:
                        # Do NOT fail listing if one file is malformed
                        pass

                    files.append({
                        "filename": p.name,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                        # Absent on an offline bundle, which credits no model.
                        "model": model,
                        "provider": provider,
                        "extractor": extractor,
                    })

            self.log.info(f"[MCP] listing stix cti files: {files}")

            return web.json_response({"files": files})

        except Exception as e:
            self.log.error(f"[MCP] list_stix_cti failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def delete_stix_cti(self, request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Body must be JSON"}, status=400)

        files = (data or {}).get("files", [])
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            return web.json_response(
                {"error": "files must be a list of strings"}, status=400
            )

        stix_dir = self.base_dir / "outputs_stix"
        stix_root = stix_dir.resolve()
        deleted = []

        for fname in files:
            # This used to join the name and unlink whatever existed, so any
            # path resolving to a file was deletable. download_stix_cti twelve
            # lines below already had the right guard.
            target = (stix_dir / fname).resolve()
            if stix_root not in target.parents:
                continue
            try:
                if target.is_file():
                    target.unlink()
                    deleted.append(fname)
            except OSError as e:
                self.log.error(f"[MCP] could not delete {fname}: {e}")

        # Report what actually went, not what was asked for.
        return web.json_response({"deleted": deleted})

    async def upload_cti_raw(self, request):
        try:
            # multipart() raises KeyError('Content-Type') rather than a 4xx
            # when the header is absent, which reached the client as a 500.
            try:
                reader = await request.multipart()
            except Exception:
                return web.json_response(
                    {"error": "Expected a multipart/form-data upload"},
                    status=400
                )
            file_part = None
            async for part in reader:
                if part.name == "file":
                    file_part = part
                    break

            if not file_part or not file_part.filename:
                return web.json_response({"error": "Missing file"}, status=400)

            filename = os.path.basename(file_part.filename)
            if not filename.lower().endswith((".txt", ".md", ".html", ".pdf")):
                return web.json_response({"error": "Unsupported file type"}, status=400)

            # 1️⃣ Save raw input (streaming, safe)
            input_dir = self.base_dir / "raw" / "uploads"
            input_dir.mkdir(parents=True, exist_ok=True)
            input_path = input_dir / filename

            data = await file_part.read()
            input_path.write_bytes(data)

            self.log.info(f"[MCP] Uploaded CTI input: {input_path}")

            # Staging only. Extraction runs from the Run Pipeline button,
            # which posts to /plugin/mcp/cti/run.
            return web.json_response({
                "status": "staged",
                "file": filename
            })

        except Exception as e:
            self.log.error(f"[MCP] CTI upload failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_cti_raw(self, request):
        try:
            uploads_dir   = self.base_dir / "raw" / "uploads"
            processed_dir = self.base_dir / "raw" / "processed"
            ir_complete   = self.base_dir / "outputs_ir" / "complete"

            items = []
            seen = set()

            def file_status(p: Path) -> str:
                """Processed means an IR exists and is no older than the file.

                The listing used to stamp a literal "processed" on everything
                in that directory, so a report that was never selected, never
                cleaned and never extracted still rendered green.
                """
                ir_path = ir_complete / f"{clean_stem(p.name)}.json"
                if not ir_path.exists():
                    return "pending"
                return (
                    "processed"
                    if ir_path.stat().st_mtime >= p.stat().st_mtime
                    else "pending"
                )

            def collect(dir_path: Path):
                out = []
                if not dir_path.exists():
                    return out

                for p in sorted(dir_path.iterdir(), key=lambda x: x.name.lower()):
                    # -------------------------
                    # DIRECTORY (NO STATUS)
                    # -------------------------
                    if p.is_dir():
                        children = []
                        for c in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                            if not c.is_file():
                                continue
                            children.append({
                                "name": c.name,
                                "size": c.stat().st_size,
                                "type": "file",
                                "status": file_status(c),
                            })
                        out.append({
                            "name": p.name,
                            "type": "dir",
                            "size": None,
                            "children": children,
                        })
                        continue

                    # -------------------------
                    # FILE
                    # -------------------------
                    if p.name in seen:
                        continue
                    seen.add(p.name)
                    out.append({
                        "name": p.name,
                        "type": "file",
                        "size": p.stat().st_size,
                        # Computed, not assumed from which directory it sits in.
                        "status": file_status(p),
                    })

                return out

            # uploads first, processed second (UI expectation)
            items.extend(collect(uploads_dir))
            items.extend(collect(processed_dir))

            return web.json_response({"items": items})

        except Exception as e:
            self.log.error(f"[MCP] list_cti_raw failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def delete_cti_raw(self, request):
        try:
            data = await request.json()
            names = data.get("files", [])

            if not names:
                return web.json_response({"error": "No files provided"}, status=400)

            uploads_dir   = self.base_dir / "raw" / "uploads"
            processed_dir = self.base_dir / "raw" / "processed"

            deleted = []

            def try_delete(base: Path, name: str) -> bool:
                if not isinstance(name, str) or not name.strip():
                    return False

                target = (base / name).resolve()
                base_resolved = base.resolve()

                # Containment. The base directory itself was previously
                # admitted, so an empty name resolved to it and the rmtree
                # below removed the whole uploads or processed directory.
                if base_resolved not in target.parents:
                    return False

                if target.exists():
                    if target.is_file():
                        target.unlink()
                    else:
                        shutil.rmtree(target)
                    return True

                return False

            for name in names:
                # try uploads first, then processed
                if try_delete(uploads_dir, name) or try_delete(processed_dir, name):
                    deleted.append(name)

            return web.json_response({"deleted": deleted})

        except Exception as e:
            self.log.error(f"[MCP] delete_cti_raw failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # Single Stix Object fetch
    async def get_stix_cti(self, request):
        try:
            data = await request.json()
            filename = data.get("filename")
            if not filename:
                return web.json_response({"error": "Missing filename"}, status=400)

            stix_dir = self.base_dir / "outputs_stix"
            target = (stix_dir / filename).resolve()

            if stix_dir.resolve() not in target.parents:
                return web.json_response({"error": "Invalid path"}, status=400)

            if not target.exists() or not target.is_file():
                return web.json_response({"error": "File not found"}, status=404)

            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except Exception as e:
                return web.json_response({"error": f"Invalid JSON: {e}"}, status=500)

            return web.json_response({"filename": filename, "data": payload})

        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def cti_status(self, request):
        """Outcome of the most recent CTI run.

        cti_run schedules the work and returns immediately, so without this
        a failure only ever reached the server log and the row in the UI
        stayed on 'pending' indefinitely.
        """
        return web.json_response(self._cti_run)

    async def view_cti_raw(self, request):
        """Return an uploaded report as text for the preview modal.

        A PDF is not readable as-is, so the extracted text from data/clean is
        preferred when the pipeline has already produced it, and pdftotext runs
        on demand otherwise. That keeps a pending PDF viewable without making
        the operator run the pipeline just to see what they uploaded.
        """
        try:
            try:
                data = await request.json()
            except Exception:
                return web.json_response({"error": "Body must be JSON"}, status=400)

            filename = (data or {}).get("filename")
            if not filename or not isinstance(filename, str):
                return web.json_response({"error": "Missing filename"}, status=400)

            # A nested upload is addressed as "<dir>/<name>", so basename is
            # too strict here. resolve() collapses any .. before the parents
            # check, which is what actually contains the read to the root.
            uploads = self.base_dir / "raw" / "uploads"
            processed = self.base_dir / "raw" / "processed"
            target = None
            for root in (uploads, processed):
                candidate = (root / filename).resolve()
                if root.resolve() in candidate.parents and candidate.is_file():
                    target = candidate
                    break
            if target is None:
                return web.json_response({"error": "File not found"}, status=404)

            suffix = target.suffix.lower()
            if suffix == ".pdf":
                clean = self.base_dir / "clean" / f"{clean_stem(target.name)}.txt"
                if clean.is_file():
                    text = clean.read_text(encoding="utf-8", errors="replace")
                else:
                    # Same missing-poppler case the cleaner handles: name the
                    # dependency rather than letting FileNotFoundError read as
                    # the report being absent.
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "pdftotext", "-layout", str(target), "-",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                    except FileNotFoundError:
                        return web.json_response(
                            {"error": "pdftotext not found. Install poppler to "
                                      "preview PDF reports."},
                            status=501,
                        )
                    out, err = await proc.communicate()
                    if proc.returncode != 0:
                        return web.json_response(
                            {"error": f"Could not read PDF: {err.decode()[:200]}"},
                            status=500,
                        )
                    text = out.decode("utf-8", errors="replace")
            else:
                text = target.read_text(encoding="utf-8", errors="replace")

            return web.json_response({
                "filename": filename,
                "kind": suffix.lstrip("."),
                "size": target.stat().st_size,
                "text": text,
            })

        except Exception as e:
            self.log.error(f"[MCP] view_cti_raw failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def get_config(self, request):
        try:
            cfg = load_config()

            # The panel used to layer the profiles itself, in JavaScript, over
            # this raw yaml. It duplicated the allowlist and skipped env
            # resolution, so it displayed "not set" for an endpoint that came
            # from MCP_LLM_API_BASE while extraction dialled it correctly.
            # Resolve it here, where the rule already lives.
            resolved = {}
            # Every LLM profile, declared or not: an absent workload profile
            # inherits the connection, and the panel has to show that.
            for profile in sorted(LLM_PROFILES):
                resolved[profile] = _without_secrets(
                    resolve_env_indirection(layered_profile(cfg, profile))
                )

            self.log.info("[MCP] get_config returning effective config")
            return web.json_response({
                "config": _without_secrets(cfg),
                "resolved": resolved,
            })
        except Exception as e:
            self.log.error(f"[MCP] get_config failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def set_config(self, request):
        """
        Persist MCP config to conf/local.yml.
        Accepts partial config blocks (llm, cti, factory).
        """
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response(
                    {"error": "Invalid config payload"},
                    status=400
                )

            payload = unwrap_config_envelope(data)

            # llm_client dispatches on an exact provider string and raises
            # "Unsupported model provider" otherwise. Catching it here names
            # the field while the operator is still looking at it, rather
            # than failing on every document at extraction time.
            invalid = [
                f"{section}.provider={cfg['provider']!r}"
                for section, cfg in payload.items()
                if isinstance(cfg, dict) and cfg.get("provider")
                and cfg["provider"] not in _VALID_PROVIDERS
            ]
            if invalid:
                return web.json_response({
                    "error": f"unsupported provider: {', '.join(invalid)}. "
                             f"Valid: {', '.join(sorted(_VALID_PROVIDERS))}"
                }, status=400)

            unknown = sorted(set(payload) - _KNOWN_SECTIONS)
            if unknown:
                return web.json_response({
                    "error": f"unknown config section: {', '.join(unknown)}. "
                             f"Valid: {', '.join(sorted(_KNOWN_SECTIONS))}."
                }, status=400)

            # The reader drops any connection key on a workload profile, so
            # accepting one here and answering "saved" persists a setting that
            # will never be read. Refuse it while the operator is still looking
            # at the field, and name the profile that does own it. The llm
            # profile has its own allowlist: it used to take any key, so an
            # Authorization header or an mlflow host landed in the file.
            def _allowed(section):
                if section in _SECTION_OVERRIDABLE:
                    return _SECTION_OVERRIDABLE[section]
                return LLM_OVERRIDABLE if section == "llm" else WORKLOAD_OVERRIDABLE

            # A credential-named key is stripped by _without_secrets below
            # rather than refused, so an older cached bundle that still posts
            # api_key can save the rest of its payload instead of failing
            # outright. Everything else outside the allowlist is a structural
            # mistake worth naming.
            misplaced = [
                f"{section}.{key}"
                for section, cfg in payload.items()
                if isinstance(cfg, dict)
                for key in sorted(cfg)
                if key not in _allowed(section) and not _is_secret(key)
            ]
            if misplaced:
                return web.json_response({
                    "error": f"not settable here: {', '.join(misplaced)}. "
                             f"The connection belongs to 'llm'; a workload "
                             f"profile may set "
                             f"{', '.join(sorted(WORKLOAD_OVERRIDABLE))}. "
                             f"Credentials belong in plugins/mcp/.env."
                }, status=400)

            bind = (payload.get("mlflow") or {}).get("host")
            if bind is not None and str(bind) not in _LOOPBACK_HOSTS:
                return web.json_response({
                    "error": f"mlflow.host {bind!r} would expose the tracking "
                             f"server, which holds every logged prompt and "
                             f"response, on a non-loopback interface. Edit "
                             f"conf/local.yml directly if that is intended."
                }, status=400)

            # fields_locked is the lock itself. Writable, it unlocks itself,
            # so it is editable only by hand in conf/local.yml.
            locked_write = [
                section for section, cfg in payload.items()
                if isinstance(cfg, dict) and "fields_locked" in cfg
            ]
            if locked_write:
                return web.json_response({
                    "error": "fields_locked cannot be set over the API; "
                             "edit conf/local.yml directly."
                }, status=400)

            # Honour the lock this endpoint used to ignore entirely.
            effective = load_config()
            blocked = [
                f"{section}.{key}"
                for section, cfg in payload.items()
                if isinstance(cfg, dict)
                for key in sorted(cfg)
                if ((effective.get(section) or {}).get("fields_locked") or {}).get(key)
            ]
            if blocked:
                return web.json_response({
                    "error": f"locked by conf/local.yml: {', '.join(blocked)}"
                }, status=400)

            conf_dir = self.root_dir / "conf"
            conf_dir.mkdir(exist_ok=True)

            local_path = conf_dir / "local.yml"

            # 1️⃣ Load existing local.yml if present
            if local_path.exists():
                with local_path.open("r", encoding="utf-8") as f:
                    existing = unwrap_config_envelope(yaml.safe_load(f) or {})
            else:
                existing = {}

            # 2️⃣ Merge the provided keys into each section.
            # Example payload: { "cti": {...} } or { "llm": {...} }
            # get_config hands back {"config": cfg}, so a client that edits
            # what it read posts that envelope straight back.
            #
            # This assigned the section outright, so a partial payload erased
            # every key it did not mention. The CTI panel posts four keys, so
            # one Save deleted a hand-pinned model, api_base or ssl_verify.
            # Removing a key is still a file edit; a POST only ever adds or
            # updates.
            for section, cfg in payload.items():
                if isinstance(cfg, dict):
                    current = existing.get(section)
                    existing[section] = (
                        deep_merge(current, cfg) if isinstance(current, dict) else cfg
                    )

            # 3️⃣ Scrub secrets from the whole file, not just the posted
            # sections, so a save also clears a key an earlier build wrote.
            existing = _without_secrets(existing)

            # 4️⃣ Write merged config back
            with local_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(existing, f, sort_keys=False)

            # 5️⃣ Reload effective config. load_config is lru_cached, so the
            # cache must be cleared or this reads back the pre-write contents.
            self.services["config"] = reload_config()

            self.log.info(f"[MCP] Config updated in {conf_dir}/local.yml")

            return web.json_response({"status": "saved"})

        except Exception as e:
            self.log.error(f"[MCP] Failed to save config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def download_stix_cti(self, request):
        try:
            data = await request.json()
            filename = data.get("filename")

            if not filename:
                return web.json_response({"error": "Missing filename"}, status=400)

            stix_dir = self.base_dir / "outputs_stix"

            target = (stix_dir / filename).resolve()

            # Hard safety check (no traversal)
            if stix_dir.resolve() not in target.parents:
                return web.json_response({"error": "Invalid path"}, status=400)

            if not target.exists() or not target.is_file():
                return web.json_response({"error": "File not found"}, status=404)

            return web.FileResponse(
                path=target,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )

        except Exception as e:
            self.log.error(f"[MCP] download_stix_cti failed: {e}")
            return web.json_response({"error": str(e)}, status=500)
