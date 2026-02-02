# plugins/mcp/app/mcp_svc.py

import logging
import json
import asyncio
from enum import Enum

import dspy
import mlflow

from app.utility.base_service import BaseService
from plugins.mcp.app.mcp_factory_client import run as factory_run
from plugins.mcp.app.mcp_planner_client import run as planner_run
from plugins.mcp.app.rag import RAGService
from plugins.mcp.app.utilities.paths import get_mcp_data_dir
from plugins.mcp.app.utilities.llm_client import (
    init_mlflow,
    get_llm_provenance,
    build_dspy_lm,
)

log = logging.getLogger("plugins.mcp")

class ExecuteStyle(Enum):
    LLMfactory = "factory"
    LLMplanner = "planner"
    RAGplanner = "rag_planner"
    RAGfactory = "rag_factory"
    RANGEplanner = "range_planner"

class MCPService(BaseService):
    def __init__(self, services):
        super().__init__()
        self.log = logging.getLogger("plugins.mcp")
        self.services = services
        self.data_svc = services.get("data_svc")
        self.file_svc = services.get("file_svc")
        self.auth_svc = services.get("auth_svc")
        self.rag_service = None
        self.log.info("[MCP] Initialized MCPService")

    # -----------------------------
    # Public entrypoint
    # -----------------------------
    async def execute(self, focus: str, prompt: str, model_config: dict, file: dict = None):
        """
        Creates the MLflow run, ends it immediately so the UI can poll,
        then resumes/updates the same run inside the async worker.
        """
        # IMPORTANT: ensure tracking URI/experiment are set BEFORE creating run
        init_mlflow(profile="service")

        # Create run and close immediately (polling can begin)
        run = mlflow.start_run(run_name="MCP Execution")
        run_id = run.info.run_id
        mlflow.set_tag("status", "queued")
        mlflow.set_tag("stage", "queued")
        mlflow.log_param("prompt", prompt)
        mlflow.end_run()

        asyncio.create_task(self._run_execution(
            focus=focus,
            prompt=prompt,
            run_id=run_id,
            run_config=model_config or {},
        ))

        return {"run_id": run_id}

    # -----------------------------
    # RAG builder (config-driven)
    # -----------------------------
    def _build_rag_service_from_files(self, filenames, embed_model: str | None, topk: int | None):
        data_dir = get_mcp_data_dir()
        bundles = []

        for name in filenames or []:
            path = data_dir / "outputs_stix" / name
            if not path.exists():
                raise FileNotFoundError(f"RAG file not found: {path}")
            with path.open("r", encoding="utf-8") as f:
                bundles.append(json.load(f))

        # Single source of truth: config
        llm_rt = get_llm_provenance("llm", runtime=True)

        # Treat empty string as unset
        embed_model = (embed_model or "").strip() or llm_rt.get("embed_model")

        # HARD FAIL instead of silently using OpenAI default embeddings
        if not embed_model:
            raise ValueError(
                "No embedding model configured. Set llm.embed_model in config or pass rag_embed_model from UI."
            )

        self.log.debug(
            "[MCP] Building RAG via llm_client | provider=%s model=%s embed_model=%s topk=%s files=%s",
            llm_rt.get("provider"),
            llm_rt.get("model"),
            embed_model,
            topk,
            filenames,
        )

        rag = RAGService(
            api_key=llm_rt["api_key"],
            log=self.log,
        )

        if topk:
            rag.topk_objects_to_retrieve = int(topk)

        rag.initialize_from_bundles(bundles, embed_model=embed_model, provider=llm_rt.get("provider"))
        return rag

    # -----------------------------
    # Background worker
    # -----------------------------
    async def _run_execution(self, focus: str, prompt: str, run_id: str, run_config: dict):
        init_mlflow(profile="service")

        # Defensive: ensure no stale active run in this task context
        try:
            mlflow.end_run()
        except Exception:
            pass

        try:
            # Resume the existing run created in execute()
            with mlflow.start_run(run_id=run_id):
                mlflow.set_tag("status", "running")
                mlflow.set_tag("stage", "initializing")

                # Build DSPy LM from config ONLY
                lm = build_dspy_lm("llm")

                rag_files = run_config.get("rag_files") or []
                rag_embed_model = (run_config.get("rag_embed_model") or "").strip() or None
                rag_topk = run_config.get("rag_topk") or 5

                use_rag = (focus in [ExecuteStyle.RAGplanner.value, ExecuteStyle.RAGfactory.value]) or bool(rag_files)

                rag_context = None
                if use_rag and rag_files:
                    mlflow.set_tag("stage", "rag_building")
                    try:
                        self.log.info("[MCP] Building RAG from files: %s", rag_files)
                        rag = self._build_rag_service_from_files(
                            filenames=rag_files,
                            embed_model=rag_embed_model,
                            topk=rag_topk,
                        )
                        rag_context = rag.get_context_for_task(prompt)
                        mlflow.set_tag("stage", "rag_ready")
                        mlflow.set_tag("rag_retrieved_count", str(len(rag_context.get("search_results", []))))
                    except Exception as e:
                        self.log.warning("[MCP] RAG build/error: %s", e)
                        mlflow.set_tag("rag_error", str(e))

                mlflow.set_tag("stage", "executing")

                # Run DSPy under a scoped context
                result = {}
                with dspy.context(lm=lm):
                    if use_rag:
                        if focus in [ExecuteStyle.LLMplanner.value, ExecuteStyle.RAGplanner.value]:
                            result = await planner_run(prompt, None, rag_context=rag_context, run_id=run_id)
                        else:
                            result = await factory_run(prompt, None, rag_context=rag_context, run_id=run_id)
                    else:
                        if focus == ExecuteStyle.LLMplanner.value:
                            result = await planner_run(prompt, None, run_id=run_id)
                        else:
                            result = await factory_run(prompt, None, run_id=run_id)

                mlflow.set_tag("stage", "complete")
                mlflow.set_tag("status", "success")

                if result.get("process_result"):
                    mlflow.set_tag("process_result_summary", str(result["process_result"])[:250])

        except Exception as e:
            self.log.error("[MCP] Execution failed: %s", e)
            try:
                with mlflow.start_run(run_id=run_id):
                    mlflow.set_tag("stage", "error")
                    mlflow.set_tag("status", "error")
                    mlflow.log_param("error", str(e))
            except Exception:
                pass
        finally:
            try:
                mlflow.end_run()
            except Exception:
                pass
