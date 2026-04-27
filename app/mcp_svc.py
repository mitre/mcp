import logging
import dspy
from app.utility.base_service import BaseService
from plugins.mcp.app.mcp_factory_client import run as factory_run
from plugins.mcp.app.mcp_planner_client import run as planner_run
from plugins.mcp.app.mcp_factory_client import get_llm_config as _yaml_llm
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
    def __init__(self, services, server_registry=None):
        super().__init__()
        self.services = services
        self.data_svc = services.get("data_svc")
        self.file_svc = services.get("file_svc")
        self.auth_svc = services.get("auth_svc")
        self.log = logging.getLogger("plugins.mcp")

        # Build RAG per run when requested
        self.rag_service = None

        # Registry of discovered MCP servers (caldera_core + any plugin-provided)
        self.server_registry = server_registry or {}
        self.log.info(
            f"[MCP] Initialized MCPService with servers: {list(self.server_registry.keys())}"
        )

    def _create_dspy_client(self, model_config: dict):
        lm = {
            "model": model_config.get("model"),
            "api_key": model_config.get("api_key"),
            "api_base": model_config.get("api_base"),
            "temperature": model_config.get("temperature"),
            "max_tokens": model_config.get("max_tokens"),
            "max_tool_calls": model_config.get("max_tool_calls"),
        }
        return lm

    async def execute(self, focus: str, prompt: str, model_config: dict, enabled_servers=None, file: dict = None):
        """Start MLflow run and launch async execution."""
        run = mlflow.start_run(run_name="MCP Execution")
        run_id = run.info.run_id
        mlflow.end_run()  # Immediately end run so polling can begin

        api_key = (model_config or {}).get("api_key")
        dspy_client = None
        if api_key:
            dspy_client = self._create_dspy_client(model_config)

        if not enabled_servers:
            enabled_servers = ["caldera_core"]

        # Launch background run, pass full config for RAG options
        asyncio.create_task(self._run_execution(
            focus=focus,
            prompt=prompt,
            run_id=run_id,
            lm_obj=dspy_client,
            run_config=model_config or {},
            enabled_servers=enabled_servers,
        ))
        return {"run_id": run_id, "enabled_servers": enabled_servers}

    def _build_rag_service_from_files(self, filenames, api_key: str, embed_model: str, topk: int):
        base_dir = Path(__file__).resolve().parent.parent / "data"
        bundles = []
        for name in filenames or []:
            path = base_dir / name
            if not path.exists():
                raise FileNotFoundError(f"RAG file not found: {path}")
            with open(path, "r", encoding="utf-8") as f:
                bundles.append(json.load(f))

        rag = RAGService(api_key=api_key, log=self.log)
        if topk:
            rag.topk_objects_to_retrieve = int(topk)
        rag.initialize_from_bundles(bundles, embed_model=embed_model or 'openai/text-embedding-3-small')
        return rag

    async def _run_execution(self, focus, prompt, run_id, lm_obj=None, run_config: dict = None, enabled_servers=None):
        """Executes the full DSPy logic in background and tracks via MLflow."""
        run_config = run_config or {}
        enabled_servers = enabled_servers or ["caldera_core"]
        try:
            # Force clear any stale MLflow context from main thread
            mlflow.end_run()
            with mlflow.start_run(run_id=run_id):
                mlflow.set_tag("stage", "initializing")
                mlflow.log_param("prompt", prompt)
                mlflow.log_param("enabled_servers", ",".join(enabled_servers))

                # Configure LM globally if provided
                if lm_obj and lm_obj.get("api_key"):
                    try:
                        yaml_cfg = _yaml_llm() or {}
                        api_base = lm_obj.get("api_base") or yaml_cfg.get("api_base")
                        # When yaml pins an alternate gateway, its model wins
                        # (gateway has a constrained model list).
                        model = (yaml_cfg.get("model")
                                 if (yaml_cfg.get("api_base") and yaml_cfg.get("model"))
                                 else lm_obj.get("model"))
                        lm_kwargs = dict(
                            model=model,
                            api_key=lm_obj.get("api_key") or yaml_cfg.get("api_key"),
                            temperature=lm_obj.get("temperature"),
                            max_tokens=lm_obj.get("max_tokens"),
                        )
                        if api_base:
                            lm_kwargs["api_base"] = api_base
                        dspy.configure(lm=dspy.LM(**lm_kwargs))
                    except Exception as e:
                        self.log.warning(f"[MCP] Failed to configure LM: {e}")

                rag_files = run_config.get("rag_files") or []
                rag_embed_model = run_config.get("rag_embed_model") or 'openai/text-embedding-3-small'
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
                common_kwargs = dict(
                    enabled_servers=enabled_servers,
                    server_registry=self.server_registry,
                )
                if use_rag:
                    if focus in [ExecuteStyle.LLMplanner.value, ExecuteStyle.RAGplanner.value]:
                        self.log.info(f"[MCP] Executing RAG-enhanced planner with prompt: {prompt}")
                        result = await planner_run(prompt, lm_obj, rag_context=rag_context, run_id=run_id, **common_kwargs)
                    else:
                        self.log.info(f"[MCP] Executing RAG-enhanced factory with prompt: {prompt}")
                        result = await factory_run(prompt, lm_obj, rag_context=rag_context, run_id=run_id, **common_kwargs)
                else:
                    if focus == ExecuteStyle.LLMplanner.value:
                        self.log.info(f"[MCP] Executing planner with prompt: {prompt}")
                        result = await planner_run(prompt, lm_obj, run_id=run_id, **common_kwargs)
                    else:
                        self.log.info(f"[MCP] Executing factory with prompt: {prompt}")
                        result = await factory_run(prompt, lm_obj, run_id=run_id, **common_kwargs)

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