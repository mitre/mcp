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

# Bound on the in-memory chat-session store. Each session holds the last
# _SESSION_TURN_CAP (prompt, response) pairs for workflows that opt in to
# chat history; older turns drop off the front. Whole sessions evict
# LRU-style when the count exceeds _SESSION_CACHE_LIMIT.
_SESSION_CACHE_LIMIT = 64
_SESSION_TURN_CAP = 8


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

        # Per-session chat history for workflows whose registration sets
        # supports_chat_history=True. session_id -> list of
        #   {"prompt": str, "response": str}
        # Author-style workflows never read or write to this map; their
        # session_ids hit it as no-ops.
        self._sessions: "collections.OrderedDict[str, list[dict]]" = collections.OrderedDict()

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

    def _session_turns(self, session_id: str) -> list[dict]:
        """Return the recorded turns for a session, or [] if unknown."""
        return self._sessions.get(session_id) or []

    def _format_session_history(self, session_id: str) -> str:
        """Render a session's prior turns as a single string for the LLM.

        Uses a simple labelled transcript format the signature docstring
        knows how to read. Empty string when there are no prior turns.
        """
        turns = self._session_turns(session_id)
        if not turns:
            return ""
        recent = turns[-_SESSION_TURN_CAP:]
        lines = []
        for turn in recent:
            lines.append(f"User: {turn['prompt']}")
            lines.append(f"Assistant: {turn['response']}")
            lines.append("")  # blank separator between turns
        return "\n".join(lines).rstrip()

    def _record_session_turn(self, session_id: str, prompt: str, response: str) -> None:
        """Append a (prompt, response) turn, capping per-session and total."""
        bucket = self._sessions.get(session_id)
        if bucket is None:
            bucket = []
            self._sessions[session_id] = bucket
        bucket.append({"prompt": prompt, "response": response})
        if len(bucket) > _SESSION_TURN_CAP:
            del bucket[: len(bucket) - _SESSION_TURN_CAP]
        self._sessions.move_to_end(session_id)
        while len(self._sessions) > _SESSION_CACHE_LIMIT:
            self._sessions.popitem(last=False)

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
                      enabled_capabilities=None, capability_settings=None,
                      session_id: str = None, disable_history: bool = False):
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

        # Resolve the session this run belongs to. The first turn auto-starts
        # a session keyed by its own run_id; follow-up turns echo the same
        # session_id back. Workflows that don't opt in still get tagged so
        # MLflow can group their (single-turn) sessions consistently.
        resolved_session_id = session_id or run_id

        asyncio.create_task(self._run_execution(
            workflow=workflow,
            prompt=prompt,
            run_id=run_id,
            session_id=resolved_session_id,
            lm_obj=lm_obj,
            enabled_servers=scoped_servers,
            enabled_capabilities=scoped_capabilities,
            capability_settings=cap_settings,
            disable_history=disable_history,
        ))
        return {
            "run_id": run_id,
            "session_id": resolved_session_id,
            "workflow_id": workflow.id,
            "enabled_servers": scoped_servers,
            "enabled_capabilities": scoped_capabilities,
            "history_disabled": bool(disable_history),
        }

    async def _run_execution(self, workflow, prompt, run_id, lm_obj,
                             enabled_servers, enabled_capabilities, capability_settings,
                             session_id=None, disable_history=False):
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
            "session_id": session_id or run_id,
            "prompt": prompt,
            "process_result": "",
            "reasoning": "",
            "trajectory": {},
        })

        # Decide once whether this run participates in chat history. The
        # session_id is always tagged for MLflow grouping; the chat_history
        # string is only built and threaded into run() when the workflow opts
        # in via supports_chat_history AND the per-request disable_history
        # flag is False. Disabling history is a clean side conversation:
        # neither read nor written, so the session thread is unaffected.
        workflow_opts_in = bool(getattr(workflow, "supports_chat_history", False))
        supports_history = workflow_opts_in and not disable_history
        effective_session_id = session_id or run_id
        prior_turn_count = (
            len(self._session_turns(effective_session_id)) if supports_history else 0
        )
        chat_history = (
            self._format_session_history(effective_session_id) if supports_history else ""
        )

        try:
            mlflow.end_run()
            with mlflow.start_run(run_id=run_id):
                mlflow.set_tag("stage", "initializing")
                mlflow.set_tag("workflow_id", workflow.id)
                mlflow.set_tag("mcp.session_id", effective_session_id)
                mlflow.set_tag("mcp.turn_index", prior_turn_count)
                if workflow_opts_in and disable_history:
                    mlflow.set_tag("mcp.history_disabled", "true")
                if supports_history:
                    mlflow.set_tag("mcp.session_history_chars", len(chat_history))
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
                run_kwargs = dict(capability_context)
                if supports_history:
                    # Workflows that opt in receive accumulated session history
                    # as a labelled transcript. Workflows that don't opt in
                    # never see the kwarg, so their signatures stay unchanged.
                    run_kwargs["chat_history"] = chat_history
                result = await workflow.run(
                    prompt,
                    lm_obj,
                    run_id=run_id,
                    enabled_servers=enabled_servers,
                    server_registry=self.server_registry,
                    **run_kwargs,
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
                    "session_id": effective_session_id,
                    "prompt": prompt,
                    "process_result": result_dict.get("process_result", ""),
                    "reasoning": result_dict.get("reasoning", ""),
                    "trajectory": result_dict.get("trajectory") or {},
                })

                # Append this turn to the session bucket only on success and
                # only for opt-in workflows. Failed runs and single-shot
                # workflows leave the session store untouched.
                if supports_history and result_dict.get("process_result"):
                    self._record_session_turn(
                        effective_session_id,
                        prompt,
                        str(result_dict.get("process_result", "")),
                    )

        except Exception as e:
            self.log.error(f"[MCP] Execution failed: {e}")
            mlflow.set_tag("stage", "error")
            mlflow.set_tag("status", "error")
            mlflow.log_param("error", str(e))
            self._record_run(run_id, {
                "status": "FAILED",
                "stage": "error",
                "workflow_id": workflow.id,
                "session_id": effective_session_id,
                "prompt": prompt,
                "process_result": "",
                "reasoning": "",
                "trajectory": {},
                "error": str(e),
            })

        finally:
            mlflow.end_run()
