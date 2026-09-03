import os
import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import sys
import mlflow
import traceback
import logging
from mlflow.tracking import MlflowClient
import asyncio
from contextlib import AsyncExitStack

from plugins.mcp.app.config import caldera_connection, llm_defaults, mlflow_settings
from plugins.mcp.app.mlflow_run import RunTracker, summarize_exception

log = logging.getLogger("plugins.mcp")
from plugins.mcp.app.dspy_env import (
    ENV_API_BASE,
    ENV_API_KEY,
    ENV_MAX_TOKENS,
    ENV_MODEL,
    ENV_PROVIDER,
    ENV_SSL_VERIFY,
    ENV_TEMPERATURE,
    ENV_TIMEOUT,
    dspy_lm_kwargs_from_settings,
)
from plugins.mcp.app.dspy_runner import safe_react_acall
from plugins.mcp.app.workflows.prompts.common import (
    CHAT_HISTORY_DESC,
    CTI_CONTEXT_DESC,
    PLAN_EXECUTE_OUTPUT_DESC,
)
from plugins.mcp.app.workflows.prompts.plan_execute import (
    PLAN_EXECUTE_AGENT_DOC,
    PLAN_EXECUTE_AGENT_WITH_CTI_DOC,
    PLAN_EXECUTE_DESCRIPTION,
    PLAN_EXECUTE_EXAMPLES,
    PLAN_EXECUTE_OPERATION_CONTEXT_DESC,
    format_plan_execute_context,
)


def _build_lm_from_settings(settings: dict) -> dspy.LM:
    """Build a dspy.LM from a resolved settings dict.

    Settings come from mcp_svc's resolver in production, or from
    llm_defaults() when run() is invoked directly without lm_obj.
    Either way the dict already has model + api_key + api_base merged.
    """
    if settings.get("offline", False):
        os.environ["LITELLM_MODEL_METADATA_LOCAL_PATH"] = "/path/to/local.json"

    api_key = settings.get("api_key") or ""
    if not api_key:
        raise ValueError(
            "API key is required but not provided. Set MCP_LLM_API_KEY in "
            "plugins/mcp/.env or enter one in the UI's Global Model Configuration."
        )

    lm_kwargs = dspy_lm_kwargs_from_settings(settings)
    return dspy.LM(**lm_kwargs)


def get_env(lm_settings=None):
    env = os.environ.copy()
    venv_site_packages = os.path.join(sys.prefix, "Lib", "site-packages")
    env['PYTHONPATH'] = (
        f"{venv_site_packages}:{env['PYTHONPATH']}"
        if 'PYTHONPATH' in env else venv_site_packages
    )

    if lm_settings:
        env[ENV_MODEL] = str(lm_settings.get('model') or 'gpt-4o')
        env[ENV_API_KEY] = str(lm_settings.get('api_key') or '')
        env[ENV_API_BASE] = str(lm_settings.get('api_base') or '')
        env[ENV_PROVIDER] = str(lm_settings.get('provider') or 'openai_compatible')
        # 0.0 is falsy, and it is the shipped value: default.yml sets
        # temperature 0 because Stage 1 parses the model's own output as JSON.
        # "or" silently exported 0.5 instead, so the setting never reached the
        # subprocess. The two lines below already guard this correctly.
        if lm_settings.get('temperature') is not None:
            env[ENV_TEMPERATURE] = str(lm_settings.get('temperature'))
        if lm_settings.get('max_tokens') is not None:
            env[ENV_MAX_TOKENS] = str(lm_settings.get('max_tokens'))
        if lm_settings.get('timeout') is not None:
            env[ENV_TIMEOUT] = str(lm_settings.get('timeout'))
        if lm_settings.get('ssl_verify') is not None:
            env[ENV_SSL_VERIFY] = str(lm_settings.get('ssl_verify')).lower()

    # Push the resolved values, not the raw environment: caldera_connection()
    # already honours the env vars, and re-reading them here would hand the
    # child a url missing the /api/v2/ suffix.
    caldera = caldera_connection()
    env['CALDERA_URL'] = caldera['url']
    env['CORE_CALDERA_API_KEY'] = caldera['api_key']

    return env

# set_tracking_uri and autolog are local state and stay eager. autolog must:
# it calls dspy.settings.configure, which pins ownership to the first asyncio
# task that reaches it, so deferring it into run() breaks the second workflow.
mlflow.set_tracking_uri(mlflow_settings()['tracking_uri'])
mlflow.dspy.autolog()

_MLFLOW_EXPERIMENT = "caldera-mcp-client-1"
_MLFLOW_EXPERIMENT_SET = False


def _ensure_mlflow():
    """set_experiment is the network call, so it cannot run at import time.

    At module scope it made importing this module block whenever the tracking
    server was down, which silently dropped both workflows from the registry.
    """
    global _MLFLOW_EXPERIMENT_SET
    if _MLFLOW_EXPERIMENT_SET:
        return
    mlflow.set_experiment(_MLFLOW_EXPERIMENT)
    _MLFLOW_EXPERIMENT_SET = True


current_dir = os.path.dirname(os.path.abspath(__file__))


class DSPyCalderaPlannerClient(dspy.Signature):
    """Plan and execute a CALDERA adversary-emulation request."""
    adversary_emulation_task: str = dspy.InputField()
    operation_context: str = dspy.InputField(
        default="", desc=PLAN_EXECUTE_OPERATION_CONTEXT_DESC,
    )
    chat_history: str = dspy.InputField(default="", desc=CHAT_HISTORY_DESC)
    process_result: str = dspy.OutputField(desc=PLAN_EXECUTE_OUTPUT_DESC)

class DSPyCalderaPlannerClientWithCTI(dspy.Signature):
    """Plan and execute a CTI-grounded CALDERA adversary-emulation request."""
    adversary_emulation_task: str = dspy.InputField()
    operation_context: str = dspy.InputField(
        default="", desc=PLAN_EXECUTE_OPERATION_CONTEXT_DESC,
    )
    cti_context: str = dspy.InputField(desc=CTI_CONTEXT_DESC)
    chat_history: str = dspy.InputField(default="", desc=CHAT_HISTORY_DESC)
    process_result: str = dspy.OutputField(
        desc=(
            PLAN_EXECUTE_OUTPUT_DESC
            + " When CTI context shaped the plan, briefly note which "
            "CTI elements drove which decisions, but keep that note "
            "secondary to the substantive results themselves."
        )
    )


DSPyCalderaPlannerClient.__doc__ = PLAN_EXECUTE_AGENT_DOC
DSPyCalderaPlannerClientWithCTI.__doc__ = PLAN_EXECUTE_AGENT_WITH_CTI_DOC


async def run(adversary_emulation_task: str, lm_obj=None,
              run_id=None, enabled_servers=None, server_registry=None,
              cti_context: str = "", chat_history: str = "",
              workflow_context: dict | None = None, denied_tools=None,
              **_extra_capability_context):
    """
    lm_obj can be:
      - a dict produced by mcp_svc.resolve_llm_config (yaml + .env + UI
        overrides already merged, with fields_locked enforced)
      - a dspy.LM instance (kept for backwards compatibility with callers
        that build their own LM)
      - None, to fall back to llm_defaults() from the shared config module
        (used by tests / direct invocation)
    """
    denied = set(denied_tools or ())
    _ensure_mlflow()
    if isinstance(lm_obj, dspy.LM):
        lm_instance = lm_obj
        lm_settings = None
        max_tool_calls = 5
    else:
        lm_settings = dict(lm_obj) if isinstance(lm_obj, dict) else llm_defaults()
        lm_instance = _build_lm_from_settings(lm_settings)
        max_tool_calls = lm_settings.get("max_tool_calls") or 5

    # Every MLflow write below is addressed to run_id. The fluent API
    # routes through a thread-local active-run stack that concurrent
    # requests share, so it retagged and terminated each other's runs and
    # minted phantom ones whenever the stack was empty.
    created_local_run = not run_id
    tracker = RunTracker.bind(run_id, _MLFLOW_EXPERIMENT, "MCP Planner Run")
    run_id = tracker.run_id

    tracker.set_tag("status", "running")
    tracker.set_tag("stage", "initializing")
    tracker.log_param("prompt", adversary_emulation_task)

    # Resolve which MCP servers to spawn
    if not enabled_servers:
        # Default to caldera_core only. cti_pipeline is opt-in: the GUI ticks
        # it on when STIX is selected, and callers can pass it explicitly.
        enabled_servers = ["caldera_core"]
    if server_registry is None:
        # Fallback used only when run() is invoked without a registry (e.g. tests).
        # mcp_server.py lives one directory up after the workflows/ split.
        core_server_path = os.path.join(os.path.dirname(current_dir), "mcp_server.py")
        # CTI pipeline server sits at the mcp plugin root.
        cti_pipeline_server_path = os.path.abspath(
            os.path.join(current_dir, "..", "..", "mcp_server.py")
        )
        server_registry = {
            "caldera_core": {
                "path": core_server_path,
                "metadata": {"display_name": "CALDERA Core", "default_enabled": True},
            },
            "cti_pipeline": {
                "path": cti_pipeline_server_path,
                # Fallback for when the server's MCP_METADATA cannot be read.
                # This copy still advertised a deploy step and detection
                # validation, neither of which exists, and the planner reads
                # descriptions to decide what it can do.
                "metadata": {
                    "display_name": "CTI Pipeline",
                    "default_enabled": False,
                    "description": "CTI pipeline tools. Server metadata unavailable.",
                },
            },
        }
    # Drop any enabled server that is not in the resolved registry so the
    # workflow degrades gracefully (e.g. caldera_core-only mode) when an
    # optional server's mcp_server.py is missing on disk.
    enabled_servers = [s for s in enabled_servers if s in server_registry]
    if not enabled_servers:
        raise ValueError(
            "no usable MCP servers - expected caldera_core (and optionally "
            "cti_pipeline) in the server registry"
        )

    tracker.log_param("enabled_servers", ",".join(enabled_servers))

    # Bump max iters when non-core servers are in the mix (realistic runs need more)
    if any(name != "caldera_core" for name in enabled_servers) and max_tool_calls < 10:
        max_tool_calls = 10
    tracker.log_param("max_tool_calls", max_tool_calls)

    try:
        async with AsyncExitStack() as stack:
            sessions = []
            for server_name in enabled_servers:
                if server_name not in server_registry:
                    raise ValueError(f"Unknown MCP server: {server_name}")
                info = server_registry[server_name]
                params = StdioServerParameters(
                    command=sys.executable,
                    args=[str(info["path"])],
                    env=get_env(lm_settings),
                )
                tracker.set_tag("stage", f"initializing MCP session: {server_name}")
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                sessions.append(session)

            # Merge tools across all sessions with collision detection
            tracker.set_tag("stage", "listing tools")
            seen = {}
            dspy_tools = []
            for server_name, session in zip(enabled_servers, sessions):
                tool_list = (await session.list_tools()).tools
                for tool in tool_list:
                    if tool.name in denied:
                        continue
                    if tool.name in seen:
                        raise ValueError(
                            f"Tool name collision: '{tool.name}' defined by both "
                            f"'{seen[tool.name]}' and '{server_name}'. "
                            f"Namespace tool names with a server prefix."
                        )
                    seen[tool.name] = server_name
                    dspy_tools.append(dspy.Tool.from_mcp_tool(session, tool))
            tracker.log_param("tool_count", len(dspy_tools))

            # Use per-call LM context, honoring lm_obj if provided
            with dspy.context(lm=lm_instance):
                tracker.set_tag("stage", "creating DSPy ReAct instance")
                # Resolve CTI context: prefer the orchestrator-supplied string,
                # fall back to formatting the legacy structured dict.
                resolved_cti = cti_context
                operation_context = format_plan_execute_context(workflow_context)
                if operation_context:
                    tracker.log_param("operation_context_preview", operation_context[:1000])
                    tracker.set_tag("operation_context_length", len(operation_context))

                if resolved_cti:
                    signature = DSPyCalderaPlannerClientWithCTI
                    tracker.log_param("cti_context_preview", resolved_cti[:1000])
                    tracker.set_tag("cti_context_length", len(resolved_cti))
                    print(f"[MCP] Passing CTI context to LLM ({len(resolved_cti)} chars)")

                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    tracker.set_tag("stage", "executing DSPy ReAct with CTI")
                    result = await safe_react_acall(
                        react,
                        adversary_emulation_task=adversary_emulation_task,
                        operation_context=operation_context,
                        cti_context=resolved_cti,
                        chat_history=chat_history,
                    )
                else:
                    signature = DSPyCalderaPlannerClient
                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    tracker.set_tag("stage", "executing DSPy ReAct")
                    result = await safe_react_acall(
                        react,
                        adversary_emulation_task=adversary_emulation_task,
                        operation_context=operation_context,
                        chat_history=chat_history,
                    )

            if chat_history:
                tracker.set_tag("chat_history_length", len(chat_history))

            # Log outputs and trajectory. The live /status endpoint reads
            # from mcp_svc's in-memory run cache, not from MLflow; these
            # writes are observability for the MLflow UI and the History
            # tab (which still scrapes tags to reconstruct trajectories
            # for past runs that have aged out of the live cache).
            tracker.set_tag("stage", "completed")
            tracker.set_tag("status", "complete")
            tracker.set_tag("reasoning", result.reasoning)
            tracker.set_tag("process_result", result.process_result)
            for k, v in result.trajectory.items():
                tracker.set_tag(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v))

            tracker.log_param("result_summary", result.process_result)
            # The orchestrator terminates the run it handed us; a run we
            # minted here is ours to close.
            if created_local_run:
                tracker.terminate("FINISHED")
            print(json.dumps(result.toDict(), indent=4))
            return {
                "process_result": result.process_result,
                "reasoning": result.reasoning,
                "trajectory": dict(result.trajectory),
            }

    except Exception as e:
        tb = traceback.format_exc()
        # A run the orchestrator handed us is the orchestrator's to classify.
        # A cancel landing during MCP session teardown arrives here as an
        # anyio group carrying BrokenResourceError and no CancelledError
        # leaf, so the type proves nothing; writing failure state would
        # stamp an immutable error param on a run the user simply stopped.
        if not created_local_run:
            log.debug(f"[MCP] Raising to the orchestrator:\n{tb}")
            raise
        print("[MCP] Exception occurred:")
        print(tb)
        tracker.set_tag("status", "failed")
        tracker.set_tag("stage", "error")
        tracker.log_param("error", summarize_exception(e))
        tracker.log_param("traceback", tb)
        tracker.terminate("FAILED")
        raise

    # Optional streaming updates (if desired for parity)
    client = MlflowClient()
    latest_thought = None
    latest_observation = None

    while True:
        run = client.get_run(run_id)
        tags = run.data.tags

        if tags.get("latest_thought") != latest_thought:
            latest_thought = tags["latest_thought"]
            client.set_tag(run_id, "frontend_thought", latest_thought)

        if tags.get("latest_observation") != latest_observation:
            latest_observation = tags["latest_observation"]
            client.set_tag(run_id, "frontend_observation", latest_observation)

        await asyncio.sleep(2)


# Workflow registration consumed by the discovery layer once it lands.
# Until then this list is dormant; the orchestrator still routes by the
# legacy ExecuteStyle string.
from plugins.mcp.app.workflows.base import Workflow  # noqa: E402

WORKFLOWS = [
    Workflow(
        id="plan_execute",
        display_name="Plan and Execute",
        description=PLAN_EXECUTE_DESCRIPTION,
        signature=DSPyCalderaPlannerClient,
        required_servers=["caldera_core"],
        optional_servers=["cti_pipeline"],
        accepted_capabilities=["cti"],
        mlflow_experiment=_MLFLOW_EXPERIMENT,
        ui_component="plan_execute.vue",
        example_prompts=PLAN_EXECUTE_EXAMPLES,
        run=run,
        supports_chat_history=True,
    ),
]
