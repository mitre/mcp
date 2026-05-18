from aiohttp import web
import logging
import mlflow
import os
import json
import yaml
import shutil
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime

from plugins.mcp.app.config import llm_defaults
from plugins.mcp.app.utilities.llm_client import load_config
from plugins.mcp.app.utilities.paths import get_mcp_data_dir, get_mcp_root
from plugins.mcp.app.cti_ingest_svc import CTIIngestService

# Fallbacks for UI fields the yaml doesn't model. The numeric LM tunables
# come back from llm_defaults() which already applies its own fallbacks;
# the RAG-specific defaults stay here because they belong to the capability
# rather than the LLM provider.
_RAG_DEFAULTS = {
    "rag_embed_model": "openai/text-embedding-3-small",
    "rag_topk": 5,
}

class McpAPI:

    def __init__(self, services):
        self.services = services
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

    @staticmethod
    def _count_catalog_items(value):
        if isinstance(value, dict):
            return sum(
                len(v) for v in value.values()
                if isinstance(v, (list, tuple, set))
            )
        if isinstance(value, (list, tuple, set)):
            return len(value)
        return 0

    def _range_supported_providers(self, profiles):
        try:
            from plugins.range.app.onprem_svc import SUPPORTED_PROVIDERS
            return sorted(SUPPORTED_PROVIDERS.keys())
        except Exception as e:
            self.log.debug(f"[MCP] Could not import Range provider registry: {e}")

        names = {
            str(p.get("provider"))
            for p in profiles
            if isinstance(p, dict) and p.get("provider")
        }
        return sorted(names)

    def _range_images_for_provider(self, range_svc, provider):
        inventory = Path(
            getattr(range_svc, "images_inventory", "plugins/range/conf/onprem_images.yml")
        )
        if not inventory.exists():
            return []

        try:
            with inventory.open("r") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            self.log.warning(f"[MCP] Could not read Range image inventory: {e}")
            return []

        images = []
        credential_store = getattr(range_svc, "credential_store", None)
        for meta in data.get("images", []) or []:
            if not isinstance(meta, dict):
                continue
            entry_provider = meta.get("provider")
            if entry_provider and entry_provider != provider:
                continue

            has_credentials = bool(meta.get("credentials"))
            username = None
            if has_credentials and credential_store is not None:
                try:
                    decrypted = credential_store.decrypt_credentials(meta)
                    if decrypted:
                        username = decrypted.get("ansible_user")
                except Exception as e:
                    self.log.debug(f"[MCP] Could not reveal Range image username: {e}")

            images.append({
                "file": meta.get("file", ""),
                "name": meta.get("name", ""),
                "os": meta.get("os", ""),
                "default_cpu": meta.get("cpus", meta.get("default_cpu", 1)),
                "default_memory": meta.get("memory", meta.get("default_memory", 4096)),
                "default_storage": meta.get("storage", meta.get("default_storage", 50)),
                "has_credentials": has_credentials,
                "username": username,
            })
        return images

    def _range_feature_catalog(self):
        range_svc = self._registered_service("range_svc")
        if range_svc is None:
            return {
                "available": False,
                "error": "Range service is not registered",
                "providers": [],
                "features": {"default": [], "custom": []},
                "feature_count": 0,
            }

        features = {"default": [], "custom": []}
        feature_error = None
        try:
            features = range_svc.get_feature_playbooks()
        except Exception as e:
            feature_error = str(e)
            self.log.warning(f"[MCP] Could not load Range feature playbooks: {e}")

        profiles = [
            p for p in getattr(range_svc, "profiles", []) or []
            if isinstance(p, dict) and p.get("range") == "onprem"
        ]
        provider_names = self._range_supported_providers(profiles)
        providers = []
        images_by_provider = {}
        for name in provider_names:
            images = self._range_images_for_provider(range_svc, name)
            images_by_provider[name] = images
            provider_profiles = [
                p.get("profile") for p in profiles
                if p.get("provider") == name and p.get("profile")
            ]
            providers.append({
                "name": name,
                "provider": name,
                "supported": True,
                "profile_count": len(provider_profiles),
                "profiles": provider_profiles,
                "image_count": len(images),
            })

        payload = {
            "available": True,
            "providers": providers,
            "features": features,
            "feature_count": self._count_catalog_items(features),
            "images_by_provider": images_by_provider,
            "endpoints": {
                "providers": "/plugin/range/onprem/providers",
                "images": "/plugin/range/onprem/images?provider=<provider>",
                "features": "/plugin/range/onprem/features",
                "microvm_substrate": "/plugin/range/microvm/substrate-status",
            },
        }
        if feature_error:
            payload["feature_error"] = feature_error
        return payload

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
                if key == "rag_embed_model":
                    payload[key] = cfg.get(key) or cfg.get("embed_model") or fallback
                else:
                    payload[key] = cfg.get(key, fallback)
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
        server registry are filtered out, since they cannot run anyway. This
        keeps a workflow card from appearing for, say, "Range Architect" when
        the RANGE plugin is not installed.
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
        """Return the MCP-facing feature catalog in one API call.

        /plugin/mcp/capabilities describes prompt-time MCP capabilities.
        Range feature playbooks are the deploy-time features Plan and
        Execute uses for infrastructure. This aggregate keeps API clients
        from stitching those separate catalogs together themselves.
        """
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
                "range": self._range_feature_catalog(),
            })
        except Exception as e:
            self.log.error(f"[MCP] Error listing feature catalog: {e}")
            return web.json_response({"error": str(e)}, status=500)

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
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
                            "modified": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z"
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
                        "process_result": run_data.params.get("process_result", ""),
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
                "process_result": run.data.params.get("process_result"),
            }

            return web.json_response(response)
        except Exception as e:
            self.log.error(f"[MCP] Error fetching run detail {run_id}: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # ===== CTI ingestion endpoints (imported from CTI branch) =====

    # CTI vue
    async def cti_run(self, request):
        try:
            data = await request.json()
            files = data.get("files")
            step = data.get("step", "all")

            if not files or not isinstance(files, list):
                return web.json_response(
                    {"error": "Missing files list"},
                    status=400
                )

            uploads = self.base_dir / "raw" / "uploads"
            processed = self.base_dir / "raw" / "processed"

            uploads.mkdir(parents=True, exist_ok=True)
            processed.mkdir(parents=True, exist_ok=True)

            # 1️⃣ Rehydrate selected items (for re-runs)
            svc = CTIIngestService()

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
            loop.run_in_executor(
                None,
                svc.run_stage,
                self.base_dir,
                step
            )

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

            rag_dir = self.base_dir / "stix_cti"
            rag_dir.mkdir(parents=True, exist_ok=True)
            target_path = rag_dir / filename
            if target_path.exists():
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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

                    # ⬇️ READ BUNDLE METADATA SAFELY
                    model = None
                    provider = None

                    try:
                        with p.open("r", encoding="utf-8") as f:
                            bundle = json.load(f)
                            model = bundle.get("x_cti_model")
                            provider = bundle.get("x_cti_provider")
                    except Exception:
                        # Do NOT fail listing if one file is malformed
                        pass

                    files.append({
                        "filename": p.name,
                        "size": stat.st_size,
                        "modified": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                        "model": model,
                        "provider": provider,
                    })

            self.log.info(f"[MCP] listing stix cti files: {files}")

            return web.json_response({"files": files})

        except Exception as e:
            self.log.error(f"[MCP] list_stix_cti failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def delete_stix_cti(self, request):
        data = await request.json()
        files = data.get("files", [])
        stix_dir = self.base_dir /"outputs_stix"

        for fname in files:
            p = stix_dir / fname
            if p.exists() and p.is_file():
                p.unlink()

        return web.json_response({"deleted": files})

    async def upload_cti_raw(self, request):
        try:
            reader = await request.multipart()
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

            # 2️⃣ Kick off pipeline (Stage 1 + 2)
            # subprocess.Popen(
            #     ["python", "app/cti_ingest_svc.py", "--base-dir", "data"],
            #     stdout=subprocess.DEVNULL,
            #     stderr=subprocess.DEVNULL,
            # )
            print(" starting cti ingest subprocess ")

            return web.json_response({
                "status": "CTI ingest started",
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
                ir_path = ir_complete / f"{p.stem}.json"
                if not ir_path.exists():
                    return "pending"
                return (
                    "processed"
                    if ir_path.stat().st_mtime >= p.stat().st_mtime
                    else "pending"
                )

            def collect(dir_path: Path, status_for_files: str | None):
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
                                "status": status_for_files,
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
                    out.append({
                        "name": p.name,
                        "type": "file",
                        "size": p.stat().st_size,
                        "status": status_for_files,
                    })

                return out

            # uploads first, processed second (UI expectation)
            items.extend(collect(uploads_dir, "pending"))
            items.extend(collect(processed_dir, "processed"))

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
                target = (base / name).resolve()
                base_resolved = base.resolve()

                # hard safety: no traversal
                if base_resolved not in target.parents and target != base_resolved:
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

    async def get_config(self, request):
        try:
            cfg = load_config()
            self.log.info("[MCP] get_config returning effective config")
            return web.json_response({"config": cfg})
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

            conf_dir = self.root_dir / "conf"
            conf_dir.mkdir(exist_ok=True)

            local_path = conf_dir / "local.yml"

            # 1️⃣ Load existing local.yml if present
            if local_path.exists():
                with local_path.open("r", encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
            else:
                existing = {}

            # 2️⃣ Update only provided top-level keys
            # Example payload: { "cti": {...} } or { "llm": {...} }
            for section, cfg in data.items():
                if isinstance(cfg, dict):
                    existing[section] = cfg

            # 3️⃣ Write merged config back
            with local_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(existing, f, sort_keys=False)

            # 4️⃣ Reload effective config in memory
            self.services["config"] = load_config()

            self.log.info(f"[MCP] Config updated in {conf_dir}/local.yml")

            return web.json_response({"status": "saved"})

        except Exception as e:
            self.log.error(f"[MCP] Failed to save config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # ===== AE end-to-end workflow runner =====

    async def run_ae_end_to_end(self, request):
        """POST /plugin/mcp/workflows/run-ae-end-to-end.

        Invokes the in-process ``ae-e2e`` workflow directly (bypassing the
        DSPy / LM pipeline used by /plugin/mcp/execute). The whole 12-stage
        state machine runs to completion in the request handler and returns
        the final state dict so callers can show stage statuses immediately
        without polling /status.

        Request body (all optional except cti_source for fresh runs):
            {
              "cti_source": "mcpBKP/.../blackcat.pdf",
              "profile_name": "blackcat-e2e",
              "dry_run": false,
              "start_stage": "deploy",
              "only_stage": null,
              "checkpoint_path": "/tmp/e2e_full_vision_state.json",
              "elk_url": "http://192.168.66.1:9200",
              "kibana_url": "http://192.168.66.1:5601",
              "microvm_base": "/tmp/timestone-microvms",
              "adversary_slug": "alphv_blackcat",
              "agents_timeout": 600,
              "operation_timeout": 1800,
              "deploy_timeout": 1200,
              "cti_timeout": 900
            }
        """
        try:
            data = await request.json() if request.body_exists else {}
        except Exception as e:
            return web.json_response(
                {"error": f"invalid JSON body: {e}"}, status=400,
            )
        if not isinstance(data, dict):
            return web.json_response(
                {"error": "request body must be a JSON object"}, status=400,
            )

        # ae-e2e is intentionally not registered in the workflow registry —
        # it duplicates plan_execute's card in the UI. The endpoint bypasses
        # the registry and instantiates AEEndToEndWorkflow directly with our
        # services dict (workflow.run requires it).
        try:
            from plugins.mcp.app.workflows.ae_e2e import AEEndToEndWorkflow
            workflow = AEEndToEndWorkflow(self.services)
            result = await workflow.run(**data)
            return web.json_response(result)
        except TypeError as e:
            return web.json_response(
                {"error": f"bad workflow arguments: {e}"}, status=400,
            )
        except Exception as e:
            self.log.exception("[MCP] ae-e2e workflow failed")
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
