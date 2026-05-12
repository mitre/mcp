import collections
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from app.utility.base_service import BaseService
import mlflow
import asyncio

from plugins.mcp.app.config import resolve_llm_config


# Where chat session history lives on disk. Co-located with RAG uploads
# under plugins/mcp/data/. Single JSON file rather than one-per-session
# because the load is once at boot and the writes happen at the end of
# successful runs, where one extra ~tens-of-KB write is invisible against
# the LLM round-trip we just finished.
_SESSIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "sessions.json"


# DSPy's chat adapter wraps each output field in '[[ ## field_name ## ]]'
# markers and emits '[[ ## completed ## ]]' to signal end-of-response. Its
# parser usually strips these, but a slightly malformed variant (e.g.
# '[[ ## completed ]]' with no closing '##') does not match the parser's
# regex and ends up in the parsed field's content. We sanitise here once so
# both the live cache and the MLflow tag and the per-turn chat history all
# get clean text instead of leaking the marker into the chat UI or back into
# the LLM on the next turn.
_DSPY_MARKER_RE = re.compile(r"\[\[\s*##\s*\w+\s*(?:##\s*)?\]\]")
_SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def _strip_dspy_markers(text: str) -> str:
    if not text:
        return text or ""
    return _DSPY_MARKER_RE.sub("", text).rstrip()


def _scrub_secrets(text: str) -> str:
    return _SECRET_RE.sub("sk-***", str(text or ""))


def _leaf_exceptions(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        leaves = []
        for child in exc.exceptions:
            leaves.extend(_leaf_exceptions(child))
        return leaves
    return [exc]


def _summarize_exception(exc: BaseException) -> str:
    leaves = _leaf_exceptions(exc)
    if not leaves:
        return _scrub_secrets(str(exc))
    primary = leaves[-1]
    summary = _scrub_secrets(str(primary)).strip() or primary.__class__.__name__
    if "failure to get a peer from the ring-balancer" in summary:
        return (
            "LLM provider unavailable: the AI Platform model gateway returned "
            "'failure to get a peer from the ring-balancer' after retries."
        )
    if "Incorrect API key provided" in summary:
        return (
            "LLM authentication failed: the configured API key was rejected by "
            "the selected provider."
        )
    return summary


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
        #
        # Loaded from _SESSIONS_FILE on boot so chat threads persist across
        # Caldera restarts. Saved on every _record_session_turn. The file is
        # only authoritative for opt-in workflows; runs that never write a
        # turn (Author, single-shot) leave nothing on disk.
        self._sessions: "collections.OrderedDict[str, list[dict]]" = (
            self._load_sessions_from_disk()
        )

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
        self._save_sessions_to_disk()

    # ------------------------------------------------------------------
    # Disk persistence for self._sessions
    # ------------------------------------------------------------------
    # Keeps opt-in workflow chat history alive across Caldera restarts.
    # The file format is intentionally trivial JSON so it can be inspected
    # or hand-edited if a session needs surgery:
    #
    #   {"schema": 1,
    #    "sessions": {"<session_id>": [{"prompt": "...", "response": "..."}, ...]}}
    #
    # Reads tolerate a missing or malformed file (returns empty); a stale
    # file with the wrong schema is dropped rather than coerced. Writes use
    # write-then-rename so a crash mid-write cannot leave a half-written
    # JSON file in place of a known-good one.

    _SESSIONS_SCHEMA_VERSION = 1

    def _load_sessions_from_disk(self) -> "collections.OrderedDict[str, list[dict]]":
        """Best-effort hydrate of the chat-history map from disk.

        Returns an empty OrderedDict if the file is absent, malformed, or
        carries an unrecognised schema version. Logs at debug level only;
        a missing sessions file is the normal first-boot state.
        """
        try:
            if not _SESSIONS_FILE.exists():
                return collections.OrderedDict()
            with open(_SESSIONS_FILE, "r", encoding="utf-8") as f:
                blob = json.load(f)
            if blob.get("schema") != self._SESSIONS_SCHEMA_VERSION:
                self.log.warning(
                    f"[MCP] Ignoring sessions file with unknown schema "
                    f"{blob.get('schema')!r}; starting fresh"
                )
                return collections.OrderedDict()
            sessions = blob.get("sessions") or {}
            if not isinstance(sessions, dict):
                return collections.OrderedDict()
            # Cap at boot too; a file that grew past the cap (e.g. limit
            # was raised then lowered) should not bypass our memory budget.
            restored: "collections.OrderedDict[str, list[dict]]" = (
                collections.OrderedDict()
            )
            for sid, turns in sessions.items():
                if not isinstance(turns, list):
                    continue
                clean_turns = [
                    t for t in turns
                    if isinstance(t, dict)
                    and isinstance(t.get("prompt"), str)
                    and isinstance(t.get("response"), str)
                ]
                if not clean_turns:
                    continue
                if len(clean_turns) > _SESSION_TURN_CAP:
                    clean_turns = clean_turns[-_SESSION_TURN_CAP:]
                restored[sid] = clean_turns
                if len(restored) >= _SESSION_CACHE_LIMIT:
                    break
            self.log.info(
                f"[MCP] Restored {len(restored)} chat session(s) from {_SESSIONS_FILE}"
            )
            return restored
        except Exception as e:
            self.log.warning(f"[MCP] Failed to load sessions file: {e}")
            return collections.OrderedDict()

    def _save_sessions_to_disk(self) -> None:
        """Atomically persist self._sessions to _SESSIONS_FILE.

        Writes to a sibling temp file in the same directory and renames
        on top of the target so a crash leaves either the previous good
        copy or the new good copy, never a truncated one. Failures here
        only log; the in-memory map is still authoritative for the
        running process.
        """
        try:
            _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            blob = {
                "schema": self._SESSIONS_SCHEMA_VERSION,
                "sessions": dict(self._sessions),
            }
            fd, tmp_path = tempfile.mkstemp(
                prefix=".sessions-", suffix=".json.tmp", dir=str(_SESSIONS_FILE.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(blob, f, ensure_ascii=False)
                os.replace(tmp_path, _SESSIONS_FILE)
            except Exception:
                # Make sure we don't leak the temp file on a write failure.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            self.log.warning(f"[MCP] Failed to persist sessions file: {e}")

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
                      workflow_context: dict | None = None,
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
            if not rag_cfg.get("api_key"):
                rag_cfg["api_key"] = resolved_lm.get("api_key", "")
            if not rag_cfg.get("api_base"):
                rag_cfg["api_base"] = resolved_lm.get("api_base", "")
            if not rag_cfg.get("embed_model"):
                rag_cfg["embed_model"] = (
                    resolved_lm.get("embed_model") or resolved_lm.get("rag_embed_model")
                )
            cap_settings["rag"] = rag_cfg

        # mlflow keeps a single "active run" per Python process; firing
        # two concurrent /plugin/mcp/execute requests would collide on
        # the second one with "Run X is already active". Use the
        # MlflowClient to mint a run record WITHOUT making it the
        # process-wide active run — the actual work in _run_execution
        # below uses `mlflow.start_run(run_id=...)` in its own context
        # manager, which is per-task and doesn't conflict.
        from mlflow.tracking import MlflowClient as _Mlc
        _exp = mlflow.get_experiment_by_name("caldera-mcp-client-1")
        _exp_id = _exp.experiment_id if _exp else "0"
        run = _Mlc().create_run(
            experiment_id=_exp_id,
            tags={"mlflow.runName": f"MCP {workflow.display_name}"},
        )
        run_id = run.info.run_id

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
            workflow_context=workflow_context if isinstance(workflow_context, dict) else {},
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
                             workflow_context=None, session_id=None,
                             disable_history=False):
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
                if isinstance(workflow_context, dict) and workflow_context:
                    mlflow.log_param(
                        "workflow_context_keys",
                        ",".join(sorted(workflow_context.keys())),
                    )

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
                if isinstance(workflow_context, dict) and workflow_context:
                    run_kwargs["workflow_context"] = workflow_context
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
                process_result = _strip_dspy_markers(
                    str(result_dict.get("process_result", ""))
                )
                reasoning = _strip_dspy_markers(
                    str(result_dict.get("reasoning", ""))
                )
                if process_result:
                    mlflow.set_tag("process_result_summary", process_result[:250])

                self._record_run(run_id, {
                    "status": "FINISHED",
                    "stage": "complete",
                    "workflow_id": workflow.id,
                    "session_id": effective_session_id,
                    "prompt": prompt,
                    "process_result": process_result,
                    "reasoning": reasoning,
                    "trajectory": result_dict.get("trajectory") or {},
                })

                # Append this turn to the session bucket only on success and
                # only for opt-in workflows. Failed runs and single-shot
                # workflows leave the session store untouched.
                if supports_history and process_result:
                    self._record_session_turn(
                        effective_session_id, prompt, process_result
                    )

        except Exception as e:
            error_summary = _summarize_exception(e)
            self.log.error(f"[MCP] Execution failed: {error_summary}")
            mlflow.set_tag("stage", "error")
            mlflow.set_tag("status", "error")
            mlflow.log_param("error", error_summary)
            self._record_run(run_id, {
                "status": "FAILED",
                "stage": "error",
                "workflow_id": workflow.id,
                "session_id": effective_session_id,
                "prompt": prompt,
                "process_result": "",
                "reasoning": "",
                "trajectory": {},
                "error": error_summary,
            })

        finally:
            mlflow.end_run()
