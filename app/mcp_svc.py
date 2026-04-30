import collections
import logging
from app.utility.base_service import BaseService
import mlflow
import asyncio

from plugins.mcp.app.config import resolve_llm_config


_LEGACY_TYPE_MAP = {
    "factory":     ("author",        []),
    "planner":     ("plan_execute",  []),
    "rag_factory": ("author",        ["rag"]),
    "rag_planner": ("plan_execute",  ["rag"]),
}

# Bound on the in-memory live-run cache. Older snapshots fall off LRU-style
# once this limit is hit; finished runs remain available via /history/run
# which still reads from MLflow.
_RUN_CACHE_LIMIT = 256


class MCPService(BaseService):
    def __init__(self, services, server_registry=None, workflow_registry=None, capability_registry=None):
        super().__init__()
        self.services = services
        self.data_svc = services.get("data_svc")
        self.file_svc = services.get("file_svc")
        self.auth_svc = services.get("auth_svc")
        self.log = logging.getLogger("plugins.mcp")

        self.rag_service = None
        self.server_registry = server_registry or {}
        self.workflow_registry = workflow_registry or {}
        self.capability_registry = capability_registry or {}

        # Live-run cache. run_id -> snapshot dict the API surfaces directly:
        #   {status, stage, workflow_id, prompt, process_result, reasoning,
        #    trajectory, error?}
        # OrderedDict gives us O(1) LRU eviction without an extra dependency.
        self._runs: "collections.OrderedDict[str, dict]" = collections.OrderedDict()

        self.log.info(
            f"[MCP] Initialized MCPService with servers={list(self.server_registry.keys())} "
            f"workflows={list(self.workflow_registry.keys())} "
            f"capabilities={list(self.capability_registry.keys())}"
        )

    def get_run(self, run_id: str) -> dict | None:
        """Return the cached snapshot for run_id, or None if not in cache."""
        return self._runs.get(run_id)

    def _record_run(self, run_id: str, snapshot: dict) -> None:
        """Write a run snapshot to the cache, evicting the oldest if full."""
        self._runs[run_id] = snapshot
        self._runs.move_to_end(run_id)
        while len(self._runs) > _RUN_CACHE_LIMIT:
            self._runs.popitem(last=False)

    def _create_dspy_client(self, model_config: dict):
        return {
            "model": model_config.get("model"),
            "api_key": model_config.get("api_key"),
            "api_base": model_config.get("api_base"),
            "temperature": model_config.get("temperature"),
            "max_tokens": model_config.get("max_tokens"),
            "max_tool_calls": model_config.get("max_tool_calls"),
        }

    async def execute(self, focus: str = None, prompt: str = "", model_config: dict = None,
                      enabled_servers=None, file: dict = None,
                      workflow_id: str = None, lm_config: dict = None,
                      enabled_capabilities=None, capability_settings=None):
        """Start an MLflow run and launch a background workflow execution.

        Accepts both the new payload shape (workflow_id + lm_config +
        enabled_capabilities + capability_settings) and the legacy one
        (focus type string + flat config). Legacy payloads are mapped via
        _LEGACY_TYPE_MAP and can be removed once the UI ships exclusively
        on the new shape.
        """
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

        if workflow_id not in self.workflow_registry:
            raise ValueError(
                f"Unknown workflow_id: {workflow_id}. "
                f"Available: {list(self.workflow_registry)}"
            )
        workflow = self.workflow_registry[workflow_id]

        allowed_servers = set(workflow.required_servers + workflow.optional_servers)
        scoped_servers = [s for s in (enabled_servers or []) if s in allowed_servers]
        for req in workflow.required_servers:
            if req not in scoped_servers:
                scoped_servers.append(req)

        scoped_capabilities = [
            c for c in (enabled_capabilities or [])
            if c in workflow.accepted_capabilities and c in self.capability_registry
        ]

        resolved_lm = resolve_llm_config(lm_config or {})
        lm_obj = self._create_dspy_client(resolved_lm)

        cap_settings = dict(capability_settings or {})
        if legacy_rag_settings is not None and "rag" not in cap_settings:
            cap_settings["rag"] = legacy_rag_settings
        if "rag" in scoped_capabilities:
            rag_cfg = dict(cap_settings.get("rag") or {})
            rag_cfg.setdefault("api_key", resolved_lm.get("api_key", ""))
            cap_settings["rag"] = rag_cfg

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
        function, so dspy.configure() is deliberately not called here (it
        raises across asyncio tasks and adds nothing).

        Live state for the polling /status endpoint is mirrored into
        self._runs as the run progresses. MLflow keeps logging tags and
        params for the History tab and the MLflow UI; it is no longer the
        source of truth for active runs.
        """
        self._record_run(run_id, {
            "status": "RUNNING",
            "stage": "initializing",
            "workflow_id": workflow.id,
            "prompt": prompt,
            "process_result": "",
            "reasoning": "",
            "trajectory": {},
        })

        try:
            mlflow.end_run()
            with mlflow.start_run(run_id=run_id):
                mlflow.set_tag("stage", "initializing")
                mlflow.set_tag("workflow_id", workflow.id)
                mlflow.log_param("workflow", workflow.id)
                mlflow.log_param("prompt", prompt)
                mlflow.log_param("enabled_servers", ",".join(enabled_servers))
                mlflow.log_param("enabled_capabilities", ",".join(enabled_capabilities))

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
                result_dict = result or {}
                if result_dict.get("process_result"):
                    mlflow.set_tag(
                        "process_result_summary",
                        str(result_dict.get("process_result", ""))[:250],
                    )

                self._record_run(run_id, {
                    "status": "FINISHED",
                    "stage": "complete",
                    "workflow_id": workflow.id,
                    "prompt": prompt,
                    "process_result": result_dict.get("process_result", ""),
                    "reasoning": result_dict.get("reasoning", ""),
                    "trajectory": result_dict.get("trajectory") or {},
                })

        except Exception as e:
            self.log.error(f"[MCP] Execution failed: {e}")
            mlflow.set_tag("stage", "error")
            mlflow.set_tag("status", "error")
            mlflow.log_param("error", str(e))
            self._record_run(run_id, {
                "status": "FAILED",
                "stage": "error",
                "workflow_id": workflow.id,
                "prompt": prompt,
                "process_result": "",
                "reasoning": "",
                "trajectory": {},
                "error": str(e),
            })

        finally:
            mlflow.end_run()
