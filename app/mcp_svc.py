import logging
from app.utility.base_service import BaseService
import mlflow
import asyncio


# Legacy ExecuteStyle string values mapped to new (workflow_id, capability_ids).
# Inbound /execute requests with `type` set to one of these are translated to
# the new payload shape. Once the UI ships the new payload exclusively, this
# shim and its callers can be deleted.
_LEGACY_TYPE_MAP = {
    "factory":     ("author",        []),
    "planner":     ("plan_execute",  []),
    "rag_factory": ("author",        ["rag"]),
    "rag_planner": ("plan_execute",  ["rag"]),
}

class MCPService(BaseService):
    def __init__(self, services, server_registry=None, workflow_registry=None, capability_registry=None):
        super().__init__()
        self.services = services
        self.data_svc = services.get("data_svc")
        self.file_svc = services.get("file_svc")
        self.auth_svc = services.get("auth_svc")
        self.log = logging.getLogger("plugins.mcp")

        # Build RAG per run when requested
        self.rag_service = None

        # Discovery registries built once at hook.enable() and handed in here.
        # The orchestrator hasn't switched to consuming workflow_registry or
        # capability_registry yet; they live on the service so /plugin/mcp/*
        # routes can expose them and so the upcoming switch is wiring-only.
        self.server_registry = server_registry or {}
        self.workflow_registry = workflow_registry or {}
        self.capability_registry = capability_registry or {}
        self.log.info(
            f"[MCP] Initialized MCPService with servers={list(self.server_registry.keys())} "
            f"workflows={list(self.workflow_registry.keys())} "
            f"capabilities={list(self.capability_registry.keys())}"
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

    async def execute(self, focus: str = None, prompt: str = "", model_config: dict = None,
                      enabled_servers=None, file: dict = None,
                      workflow_id: str = None, lm_config: dict = None,
                      enabled_capabilities=None, capability_settings=None):
        """Start an MLflow run and launch a background workflow execution.

        Accepts both the new payload shape and the legacy one. The HTTP layer
        decides which fields to fill; this method maps the legacy ones onto
        the new ones via _LEGACY_TYPE_MAP.

        New payload (preferred):
          workflow_id, prompt, lm_config, enabled_servers, enabled_capabilities,
          capability_settings

        Legacy payload (supported until the UI catches up):
          focus (== "factory"|"planner"|"rag_factory"|"rag_planner"),
          prompt, model_config, enabled_servers
        """
        # ---- 1. Translate legacy payload into the new shape ----
        legacy_rag_settings = None
        if workflow_id is None and focus is not None:
            mapped = _LEGACY_TYPE_MAP.get(focus)
            if mapped is None:
                raise ValueError(f"Unknown legacy execute type: {focus}")
            workflow_id, mapped_caps = mapped
            enabled_capabilities = list(enabled_capabilities or [])
            for c in mapped_caps:
                if c not in enabled_capabilities:
                    enabled_capabilities.append(c)
            # Legacy clients also enable RAG implicitly when they include
            # rag_files in model_config, even when type is plain factory/planner.
            mc = model_config or {}
            if mc.get("rag_files") and "rag" not in enabled_capabilities:
                enabled_capabilities.append("rag")
            if "rag" in enabled_capabilities:
                legacy_rag_settings = {
                    "rag_files": mc.get("rag_files") or [],
                    "topk": mc.get("rag_topk"),
                    "embed_model": mc.get("rag_embed_model"),
                }
            if lm_config is None:
                lm_config = mc

        if workflow_id is None:
            raise ValueError("execute() requires either workflow_id or focus")

        # ---- 2. Resolve workflow + filter inputs against its declared scope ----
        if workflow_id not in self.workflow_registry:
            raise ValueError(
                f"Unknown workflow_id: {workflow_id}. "
                f"Available: {list(self.workflow_registry)}"
            )
        workflow = self.workflow_registry[workflow_id]

        allowed_servers = set(workflow.required_servers + workflow.optional_servers)
        scoped_servers = [s for s in (enabled_servers or []) if s in allowed_servers]
        # Required servers always run, even if the caller didn't include them.
        for req in workflow.required_servers:
            if req not in scoped_servers:
                scoped_servers.append(req)

        scoped_capabilities = [
            c for c in (enabled_capabilities or [])
            if c in workflow.accepted_capabilities and c in self.capability_registry
        ]

        # ---- 3. Build LM dict + merge per-capability settings ----
        lm_obj = None
        if lm_config and lm_config.get("api_key"):
            lm_obj = self._create_dspy_client(lm_config)

        cap_settings = dict(capability_settings or {})
        # Hand the legacy rag settings forward under the new key.
        if legacy_rag_settings is not None and "rag" not in cap_settings:
            cap_settings["rag"] = legacy_rag_settings
        # The rag capability needs an api_key for embedding; inject from lm_config
        # when the caller didn't supply one explicitly.
        if "rag" in scoped_capabilities and lm_obj:
            rag_cfg = dict(cap_settings.get("rag") or {})
            rag_cfg.setdefault("api_key", lm_obj.get("api_key", ""))
            cap_settings["rag"] = rag_cfg

        # ---- 4. Start MLflow run and launch the background task ----
        run = mlflow.start_run(run_name=f"MCP {workflow.display_name}")
        run_id = run.info.run_id
        mlflow.end_run()

        asyncio.create_task(self._run_execution(
            workflow=workflow,
            prompt=prompt,
            run_id=run_id,
            lm_obj=lm_obj,
            enabled_servers=scoped_servers,
            enabled_capabilities=scoped_capabilities,
            capability_settings=cap_settings,
        ))
        return {
            "run_id": run_id,
            "workflow_id": workflow.id,
            "enabled_servers": scoped_servers,
            "enabled_capabilities": scoped_capabilities,
        }

    async def _run_execution(self, workflow, prompt, run_id, lm_obj,
                             enabled_servers, enabled_capabilities, capability_settings):
        """Run a workflow end-to-end in the background, tracking via MLflow.

        Per-request LM is set via dspy.context() inside each workflow's run()
        function, so we deliberately do not call dspy.configure() from this
        async task (it raises across tasks and adds nothing).
        """
        try:
            mlflow.end_run()
            with mlflow.start_run(run_id=run_id):
                mlflow.set_tag("stage", "initializing")
                mlflow.set_tag("workflow_id", workflow.id)
                mlflow.log_param("workflow", workflow.id)
                mlflow.log_param("prompt", prompt)
                mlflow.log_param("enabled_servers", ",".join(enabled_servers))
                mlflow.log_param("enabled_capabilities", ",".join(enabled_capabilities))

                # ---- Run capabilities sequentially. Each contributes kwargs
                #      that get merged into the workflow's run() context. ----
                capability_context = {}
                for cap_id in enabled_capabilities:
                    cap = self.capability_registry[cap_id]
                    if cap.enrich is None:
                        continue
                    settings = capability_settings.get(cap_id, {})
                    mlflow.set_tag(f"capability_{cap_id}_stage", "running")
                    try:
                        self.log.info(f"[MCP] Running capability '{cap_id}' enrich()")
                        contrib = await cap.enrich(prompt, settings) or {}
                        capability_context.update(contrib)
                        mlflow.set_tag(f"capability_{cap_id}_stage", "complete")
                        mlflow.set_tag(
                            f"capability_{cap_id}_fields",
                            ",".join(sorted(contrib.keys())),
                        )
                    except Exception as e:
                        mlflow.set_tag(f"capability_{cap_id}_stage", "error")
                        self.log.warning(f"[MCP] Capability '{cap_id}' enrich failed: {e}")

                # ---- Invoke the workflow ----
                if workflow.run is None:
                    raise RuntimeError(f"Workflow {workflow.id} has no run() function")

                self.log.info(
                    f"[MCP] Executing workflow '{workflow.id}' with prompt={prompt!r}"
                )
                mlflow.set_tag("stage", "executing workflow")
                result = await workflow.run(
                    prompt,
                    lm_obj,
                    run_id=run_id,
                    enabled_servers=enabled_servers,
                    server_registry=self.server_registry,
                    **capability_context,
                )

                mlflow.set_tag("stage", "complete")
                mlflow.set_tag("status", "success")
                if (result or {}).get("process_result"):
                    mlflow.set_tag(
                        "process_result_summary",
                        str(result.get("process_result", ""))[:250],
                    )

        except Exception as e:
            self.log.error(f"[MCP] Execution failed: {e}")
            mlflow.set_tag("stage", "error")
            mlflow.set_tag("status", "error")
            mlflow.log_param("error", str(e))

        finally:
            mlflow.end_run()