from aiohttp import web
import logging
import mlflow
import os
import json
import yaml
import shutil
from pathlib import Path
from datetime import datetime
import subprocess
from plugins.mcp.app.utilities.cti_llm_client import load_config

class McpAPI:

    def __init__(self, services):
        self.services = services
        self.mcp_svc = services.get("mcp_svc")
        self.log = logging.getLogger("plugins.mcp")
        self.log.info("[MCP] Initialized McpAPI")

    async def execute(self, request):
        self.log.info("[MCP] Executing request")
        try:
            data = await request.json()
            self.log.info(f"[MCP] Request data: {data}")
            user_input = data.get("text", "")
            self.log.info(f"[MCP] User input: {user_input}")
            focus = data.get("type", "factory")  # Default to factory if not specified
            self.log.info(f"[MCP] Execution focus: {focus}")
            model_config = data.get("config")
            self.log.info(f"[MCP] Config received")

            if not user_input:
                return web.json_response({"error": 'Missing "text" in request'}, status=400)

            # Pass both focus and prompt to the service
            result = await self.mcp_svc.execute(focus=focus, prompt=user_input, model_config=model_config)
            return web.json_response(result)

        except Exception as e:
            self.log.error(f"[MCP] Error executing request: {str(e)}")
            return web.json_response({"error": str(e)}, status=500)

    async def status(self, request):
        run_id = request.query.get("run_id")
        if not run_id:
            return web.json_response({"error": "Missing run_id"}, status=400)
        try:
            client = mlflow.tracking.MlflowClient()
            run = client.get_run(run_id)
            
            # Extract full trajectory
            trajectory = {
                k: v for k, v in run.data.tags.items()
                if k.startswith("thought_") or k.startswith("observation_") or k.startswith("tool_name_") or k.startswith("tool_args_")
            }
            
            response = {
                "run_id": run_id,
                "status": run.info.status,
                "stage": run.data.tags.get("stage"),
                "prompt": run.data.params.get("prompt"),
                "reasoning": run.data.tags.get("reasoning"),
                "process_result": run.data.params.get("process_result"),
                "trajectory": trajectory
            }
            self.log.info(f"[MCP] Status for run {run_id} retrieved")

            return web.json_response(response)

        except Exception as e:
            self.log.error(f"[MCP] Error fetching run {run_id}: {e}")
            return web.json_response({"error": str(e)}, status=500)

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

            base_dir = (
                Path(__file__).resolve().parents[2]
                / "plugins" / "mcp" / "data" / "stix_cti"
            )
            base_dir.mkdir(parents=True, exist_ok=True)

            target_path = base_dir / filename
            if target_path.exists():
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                target_path = base_dir / f"{target_path.stem}_{ts}.json"

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
        base_dir = (
            Path(__file__).resolve().parents[2]
            / "plugins" / "mcp" / "data" / "stix_cti"
        )

        files = []
        if base_dir.exists():
            for p in base_dir.glob("*.json"):
                stat = p.stat()
                files.append({
                    "filename": p.name,
                    "size": stat.st_size,
                    "modified": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z"
                })

        return web.json_response({"files": files})

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
            plugin_root = Path(__file__).resolve().parents[1]
            input_dir = (plugin_root / "data/raw/uploads").resolve()
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
            plugin_root = Path(__file__).resolve().parents[1]
            raw_dir = plugin_root / "data/raw/uploads"

            if not raw_dir.exists():
                return web.json_response({"items": []})

            items = []

            # 1️⃣ Directories first
            for p in sorted(raw_dir.iterdir(), key=lambda x: x.name.lower()):
                if p.is_dir():
                    children = []
                    for c in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                        if c.is_file():
                            stat = c.stat()
                            children.append({
                                "name": c.name,
                                "size": stat.st_size,
                                "type": "file",
                            })

                    items.append({
                        "name": p.name,
                        "type": "dir",
                        "children": children,
                    })

            # 2️⃣ Then loose files
            for p in sorted(raw_dir.iterdir(), key=lambda x: x.name.lower()):
                if p.is_file():
                    stat = p.stat()
                    items.append({
                        "name": p.name,
                        "size": stat.st_size,
                        "type": "file",
                    })

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

            plugin_root = Path(__file__).resolve().parents[1]
            raw_dir = plugin_root / "data/raw/uploads"

            deleted = []

            for name in names:
                # resolve and hard-anchor to uploads dir (no traversal)
                target = (raw_dir / name).resolve()
                raw_dir_resolved = raw_dir.resolve()

                if raw_dir_resolved not in target.parents and target != raw_dir_resolved:
                    continue

                if target.is_file():
                    target.unlink()
                    deleted.append(name)

                elif target.is_dir():
                    shutil.rmtree(target)
                    deleted.append(name)

            return web.json_response({"deleted": deleted})

        except Exception as e:
            self.log.error(f"[MCP] delete_cti_raw failed: {e}")
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

            plugin_root = Path(__file__).resolve().parents[1]  # plugins/mcp
            conf_dir = plugin_root / "conf"
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

def setup_routes(app, mcp_api: McpAPI):
    app.router.add_post("/plugin/mcp/execute", mcp_api.execute)
    app.router.add_get("/plugin/mcp/status", mcp_api.status)
    app.router.add_post("/plugin/mcp/rag/upload", mcp_api.upload_rag)
    app.router.add_get("/plugin/mcp/rag/list", mcp_api.list_rag)