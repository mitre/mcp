import logging
import dspy
from app.utility.base_service import BaseService
from plugins.mcp.app.mcp_factory_client import run as factory_run
from plugins.mcp.app.mcp_planner_client import run as planner_run
from plugins.mcp.app.rag import RAGService
from enum import Enum
import mlflow
import asyncio
import json
from pathlib import Path

class ExecuteStyle(Enum):
    LLMfactory = "factory"
    LLMplanner = "planner"
    RAGplanner = "rag_planner"
    RAGfactory = "rag_factory"

class MCPService(BaseService):
    def __init__(self, services):
        super().__init__()
        self.services = services
        self.data_svc = services.get("data_svc")
        self.file_svc = services.get("file_svc")
        self.auth_svc = services.get("auth_svc")
        self.log = logging.getLogger("plugins.mcp")

        # Build RAG per run when requested
        self.rag_service = None
        self.log.info("[MCP] Initialized MCPService")

    def _create_dspy_client(self, model_config: dict):
        lm = {
            "model": model_config.get("model"),
            "api_key": model_config.get("api_key"),
            "temperature": model_config.get("temperature"),
            "max_tokens": model_config.get("max_tokens"),
            "max_tool_calls": model_config.get("max_tool_calls"),
            "api_base": model_config.get("api_base")
        }
        return lm

    async def execute(self, focus: str, prompt: str, model_config: dict, file: dict = None):
        """Start MLflow run and launch async execution."""
        run = mlflow.start_run(run_name="MCP Execution")
        run_id = run.info.run_id
        mlflow.end_run()  # Immediately end run so polling can begin

        api_key = (model_config or {}).get("api_key")
        dspy_client = None
        if api_key:
            dspy_client = self._create_dspy_client(model_config)

        # Launch background run, pass full config for RAG options
        asyncio.create_task(self._run_execution(
            focus=focus,
            prompt=prompt,
            run_id=run_id,
            lm_obj=dspy_client,
            run_config=model_config or {}
        ))
        return {"run_id": run_id}

    def _build_rag_service_from_files(self, filenames, api_key: str, embed_model: str, topk: int, api_base: str = None):
        base_dir = Path(__file__).resolve().parent.parent / "data"
        bundles = []
        for name in filenames or []:
            path = base_dir / name
            if not path.exists():
                raise FileNotFoundError(f"RAG file not found: {path}")
            with open(path, "r", encoding="utf-8") as f:
                bundles.append(json.load(f))

        rag = RAGService(api_key=api_key, api_base=api_base, log=self.log)
        if topk:
            rag.topk_objects_to_retrieve = int(topk)
        rag.initialize_from_bundles(bundles, embed_model=embed_model or 'nvidia/llama-3.2-nv-embedqa-1b-v2')
        return rag

    async def _run_execution(self, focus, prompt, run_id, lm_obj=None, run_config: dict = None):
        """Executes the full DSPy logic in background and tracks via MLflow."""
        run_config = run_config or {}
        try:
            # Force clear any stale MLflow context from main thread
            mlflow.end_run()
            with mlflow.start_run(run_id=run_id):
                mlflow.set_tag("stage", "initializing")
                mlflow.log_param("prompt", prompt)

                # Configure LM globally if provided
                if lm_obj and lm_obj.get("api_key"):
                    try:
                        lm = dspy.LM(
                            model=f"nvidia_nim/" + lm_obj.get("model"),
                            api_key=lm_obj.get("api_key"),
                            api_base=lm_obj.get("api_base"),
                            temperature=lm_obj.get("temperature"),
                            max_tokens=lm_obj.get("max_tokens"),
                        )
                    except Exception as e:
                        self.log.warning(f"[MCP] Failed to configure LM: {e}")

                rag_files = run_config.get("rag_files") or []
                rag_embed_model = run_config.get("rag_embed_model") or 'nvidia/llama-3.2-nv-embedqa-1b-v2'
                rag_topk = run_config.get("rag_topk")

                # Use RAG if explicitly requested via focus or if files were selected
                use_rag = (focus in [ExecuteStyle.RAGplanner.value, ExecuteStyle.RAGfactory.value]) or bool(rag_files)

                rag_context = None
                if use_rag and rag_files:
                    try:
                        self.log.info(f"[MCP] Building RAG from files: {rag_files}")
                        rag = self._build_rag_service_from_files(
                            filenames=rag_files,
                            api_key=(lm_obj or {}).get("api_key"),
                            api_base=(lm_obj or {}).get("api_base"),
			    embed_model=rag_embed_model,
                            topk=rag_topk or 5
                        )
                        rag_context = rag.get_context_for_task(prompt)
                        # Log RAG retrieval process (use different namespace to avoid collision with LLM thoughts)
                        for i, thought in enumerate(rag_context.get("thoughts", [])):
                            mlflow.set_tag(f"rag_retrieval_step_{i}", thought)

                        # Log which CTI objects were retrieved
                        search_results = rag_context.get('search_results', [])
                        for i, result in enumerate(search_results):
                            result_name = result.split(" | ")[0] if " | " in result else result[:100]
                            mlflow.set_tag(f"rag_retrieved_object_{i}", result_name)

                        mlflow.set_tag("rag_tool_name", "get_context_for_task")
                        mlflow.set_tag("rag_tool_args", json.dumps({"query": prompt, "rag_files": rag_files}))
                        self.log.info(f"[MCP] RAG retrieved {len(search_results)} CTI objects")
                    except Exception as e:
                        self.log.warning(f"[MCP] RAG build/error: {e}")

                # Execute appropriate pipeline
                result = {}
                if use_rag:
                    if focus in [ExecuteStyle.LLMplanner.value, ExecuteStyle.RAGplanner.value]:
                        self.log.info(f"[MCP] Executing RAG-enhanced planner with prompt: {prompt}")
                        if lm:
                            with dspy.context(lm=lm):  # ✅ Context entered here!
                                result = await planner_run(prompt, lm_obj, rag_context=rag_context, run_id=run_id)
                        else:
                            result = await planner_run(prompt, lm_obj, rag_context=rag_context, run_id=run_id)
                    else:
                        self.log.info(f"[MCP] Executing RAG-enhanced factory with prompt: {prompt}")
                        if lm:
                            with dspy.context(lm=lm):  # ✅ Context entered here!
                                result = await factory_run(prompt, lm_obj, rag_context=rag_context, run_id=run_id)
                        else:
                            result = await factory_run(prompt, lm_obj, rag_context=rag_context, run_id=run_id)
                else:
                    if focus == ExecuteStyle.LLMplanner.value:
                        self.log.info(f"[MCP] Executing planner with prompt: {prompt}")
                        if lm:
                            with dspy.context(lm=lm):  # ✅ Context entered here!
                                result = await planner_run(prompt, lm_obj, run_id=run_id)
                        else:
                            result = await planner_run(prompt, lm_obj, run_id=run_id)
                    else:
                        self.log.info(f"[MCP] Executing factory with prompt: {prompt}")
                        if lm:
                            with dspy.context(lm=lm):  # ✅ Context entered here!
                                result = await factory_run(prompt, lm_obj, run_id=run_id)
                        else:
                            result = await factory_run(prompt, lm_obj, run_id=run_id)
                            
                mlflow.set_tag("stage", "complete")
                mlflow.set_tag("status", "success")
                # Store process_result as a tag instead of param to avoid conflicts
                # (the client already logs it as a param)
                if result.get("process_result"):
                    mlflow.set_tag("process_result_summary", str(result.get("process_result", ""))[:250])

        except Exception as e:
            self.log.error(f"[MCP] Execution failed: {e}")
            mlflow.set_tag("stage", "error")
            mlflow.set_tag("status", "error")
            mlflow.log_param("error", str(e))

        finally:
            mlflow.end_run()
