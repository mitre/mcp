from aiohttp import web
import logging
import mlflow
import os
import json
import yaml
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
import subprocess
from plugins.mcp.app.utilities.cti_llm_client import load_config
from plugins.mcp.app.cti_ingest_svc import CTIIngestService
from plugins.mcp.app.utilities.paths import get_mcp_data_dir, get_mcp_root
class McpAPI:

    def __init__(self, services):
        self.services = services
        self.mcp_svc = services.get("mcp_svc")
        self.log = logging.getLogger("plugins.mcp")
        self.log.info("[MCP] Initialized McpAPI")
        self.base_dir = get_mcp_data_dir()
        self.root_dir = get_mcp_root()


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

            self.base_dir.mkdir(parents=True, exist_ok=True)

            rag_dir = self.base_dir / "stix_cti"
            rag_dir.mkdir(parents=True, exist_ok=True)

            target_path = rag_dir / filename
            if target_path.exists():
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                target_path = rag_dir / f"{target_path.stem}_{ts}.json"

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



def setup_routes(app, mcp_api: McpAPI):
    app.router.add_post("/plugin/mcp/execute", mcp_api.execute)
    app.router.add_get("/plugin/mcp/status", mcp_api.status)
    app.router.add_post("/plugin/mcp/rag/upload", mcp_api.upload_rag)
