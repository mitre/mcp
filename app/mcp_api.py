from aiohttp import web
import logging
import mlflow
import os
import json
from pathlib import Path
from datetime import datetime

from plugins.mcp.app.config import llm_defaults

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

    async def execute(self, request):
        """POST /plugin/mcp/execute.

        New payload shape (preferred):
            {
              "text": "...",
              "workflow_id": "author" | "plan_execute" | ...,
              "lm_config": { model, api_key, api_base, temperature, max_tokens, max_tool_calls },
              "enabled_servers": ["caldera_core", ...],
              "enabled_capabilities": ["rag", ...],
              "capability_settings": { "rag": { "rag_files": [...], "topk": 5, "embed_model": "..." } }
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
            # Optional. Absent on the first turn of a chat; the response
            # echoes back the assigned session_id so the client can pass it
            # on follow-up turns. Workflows that opt out of chat history
            # ignore this value entirely.
            session_id = data.get("session_id")

            # Legacy fields (only used when workflow_id is absent)
            focus = data.get("type")
            model_config = data.get("config")

            self.log.info(
                f"[MCP] workflow_id={workflow_id} legacy_type={focus} "
                f"session_id={session_id} "
                f"enabled_servers={enabled_servers} "
                f"enabled_capabilities={enabled_capabilities}"
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
                session_id=session_id,
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
                "fields_locked": cfg.get("fields_locked") or {},
            }
            for key, fallback in _RAG_DEFAULTS.items():
                payload[key] = cfg.get(key, fallback)
            return web.json_response(payload)
        except Exception as e:
            self.log.error(f"[MCP] Error fetching defaults: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_servers(self, request):
        """Return discovered MCP server registry for UI toggles."""
        try:
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
            return web.json_response({"servers": servers})
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
            return web.json_response({"workflows": workflows})
        except Exception as e:
            self.log.error(f"[MCP] Error listing workflows: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_capabilities(self, request):
        """Return discovered Capability registry so the UI can render settings panels."""
        try:
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
            return web.json_response({"capabilities": capabilities})
        except Exception as e:
            self.log.error(f"[MCP] Error listing capabilities: {e}")
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

        self.log.info(f"[MCP] Status for run {run_id} served from cache")
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

