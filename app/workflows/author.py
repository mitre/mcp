import os
import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import sys
import mlflow
import traceback
import logging
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
from plugins.mcp.app.workflows.prompts.common import CTI_CONTEXT_DESC


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

_MLFLOW_EXPERIMENT = "caldera-mcp-FACTORY-client-1"
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

_AUTHOR_OUTPUT_DESC = (
    "The substantive answer to the user's request. Include the actual data "
    "produced or observed: the names and ids of every ability you created, "
    "the name and id of any adversary you authored, and any tool outputs "
    "the user asked about. When listing items, use a short bulleted or "
    "numbered list with the real names from the observations, not "
    "placeholders. Do NOT narrate which tools you called or describe your "
    "methodology. Do NOT say things like 'I first listed X, then I created "
    "Y'. The user wants the artifacts and the data, not a recap of how "
    "you got them. If a tool failed and you could not complete part of the "
    "request, say so clearly and name what is missing, but still return "
    "whatever you did create or retrieve."
)


class DSPyCalderaFactoryClient(dspy.Signature):
    """You are an ability factory for the Caldera adversary emulation platform.
    You have access to MCP tool servers that wrap Caldera's core API and any
    installed plugins. Your job is to AUTHOR reusable artifacts: abilities and
    adversaries. Do NOT run operations or deploy infrastructure.

    Use only the tools needed to create the requested artifact. If a tool
    deploys VMs, runs operations, or performs destructive actions, do not
    call it unless the user's request explicitly requires it.

    When you produce process_result, return the substantive content the
    user asked for (real ids, names, ability lists), not a recap of the
    tools you called.
    """

    adversary_emulation_task: str = dspy.InputField()
    process_result: str = dspy.OutputField(desc=_AUTHOR_OUTPUT_DESC)

class DSPyCalderaFactoryClientWithCTI(dspy.Signature):
    """You are an ability factory for the Caldera adversary emulation platform,
    enhanced with Cyber Threat Intelligence (CTI) data. You have access to MCP
    tool servers that wrap Caldera's core API and any installed plugins. Your
    job is to AUTHOR reusable artifacts: abilities and adversaries informed by
    CTI. Do NOT run operations or deploy infrastructure.

    Use only the tools needed to create the requested artifact. If a tool
    deploys VMs, runs operations, or performs destructive actions, do not
    call it unless the user's request explicitly requires it.

    When you produce process_result, return the substantive content the
    user asked for (real ids, names, ability lists), not a recap of the
    tools you called.
    """

    adversary_emulation_task: str = dspy.InputField()
    cti_context: str = dspy.InputField(desc=CTI_CONTEXT_DESC)
    process_result: str = dspy.OutputField(
        desc=(
            _AUTHOR_OUTPUT_DESC
            + " When CTI context shaped what you authored, briefly note "
            "which CTI elements drove which design choices, but keep that "
            "note secondary to the substantive results themselves."
        )
    )


async def run(adversary_emulation_task: str, lm_obj=None, run_id=None, enabled_servers=None, server_registry=None, cti_context: str = "", workflow_context: dict | None = None, denied_tools=None,
              **_extra_capability_context):
    # cti_context is the attached intel, already rendered by the cti
    # capability. **_extra_capability_context absorbs unknown kwargs from
    # future capabilities so adding one doesn't break this signature.
    #
    # lm_obj is the dict mcp_svc produces from resolve_llm_config (yaml + .env
    # + UI overrides, with fields_locked enforced). Workflows trust it; they
    # do not re-merge yaml here. Tests that call run() directly without
    # lm_obj fall back to the same yaml-resolved defaults.
    denied = set(denied_tools or ())
    _ensure_mlflow()
    lm_settings = dict(lm_obj) if lm_obj else llm_defaults()
    max_tool_calls = lm_settings.get("max_tool_calls") or 5

    # Every MLflow write below is addressed to run_id. The fluent API
    # routes through a thread-local active-run stack that concurrent
    # requests share, so it retagged and terminated each other's runs and
    # minted phantom ones whenever the stack was empty.
    created_local_run = not run_id
    tracker = RunTracker.bind(run_id, _MLFLOW_EXPERIMENT, "MCP Ability Factory")
    run_id = tracker.run_id

    # Both credentials are checked here rather than at dspy.LM() so the
    # failure lands before the AsyncExitStack spawns MCP subprocesses.
    missing = next(
        (f for f in ("api_key", "api_base") if not lm_settings.get(f)), None
    )
    if missing:
        error_msg = f"{missing} is required but not provided. Please set it in the Global Model Configuration."
        print(f"[MCP] ERROR: {error_msg}")
        tracker.set_tag("status", "failed")
        tracker.set_tag("stage", "error")
        tracker.log_param("error", error_msg)
        tracker.log_param("prompt", adversary_emulation_task)
        if created_local_run:
            tracker.terminate("FAILED")
        raise ValueError(error_msg)

    tracker.set_tag("status", "running")
    tracker.set_tag("stage", "initializing")
    tracker.log_param("prompt", adversary_emulation_task)

    # Resolve which MCP servers to spawn
    if not enabled_servers:
        enabled_servers = ["caldera_core"]
    if server_registry is None:
        # Fallback used only when run() is invoked without a registry (e.g. tests).
        # mcp_server.py lives one directory up after the workflows/ split.
        server_registry = {
            "caldera_core": {
                "path": os.path.join(os.path.dirname(current_dir), "mcp_server.py"),
                "metadata": {"display_name": "CALDERA Core", "default_enabled": True},
            }
        }

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

            # Use context to set LM for this task/run
            lm_kwargs = dspy_lm_kwargs_from_settings(lm_settings)
            with dspy.context(lm=dspy.LM(**lm_kwargs)):
                tracker.set_tag("stage", "creating DSPy ReAct instance")

                # Resolve CTI context: prefer the orchestrator-supplied string,
                resolved_cti = cti_context

                if resolved_cti:
                    signature = DSPyCalderaFactoryClientWithCTI
                    tracker.log_param("cti_context_preview", resolved_cti[:1000])
                    tracker.set_tag("cti_context_length", len(resolved_cti))
                    print(f"[MCP] Passing CTI context to LLM ({len(resolved_cti)} chars)")

                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    tracker.set_tag("stage", "executing DSPy ReAct with CTI")
                    result = await safe_react_acall(
                        react,
                        adversary_emulation_task=adversary_emulation_task,
                        cti_context=resolved_cti,
                    )
                else:
                    signature = DSPyCalderaFactoryClient
                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    tracker.set_tag("stage", "executing DSPy ReAct")
                    result = await safe_react_acall(
                        react,
                        adversary_emulation_task=adversary_emulation_task,
                    )

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

            print(json.dumps(result.toDict(), indent=4))

            # The orchestrator terminates the run it handed us; a run we
            # minted here is ours to close.
            if created_local_run:
                tracker.terminate("FINISHED")

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


# Workflow registration consumed by the discovery layer once it lands.
# Until then, this list is dormant; the orchestrator still routes by the
# legacy ExecuteStyle string. Both registration paths will coexist for
# one or two commits and then ExecuteStyle will be removed.
from plugins.mcp.app.workflows.base import Workflow  # noqa: E402

WORKFLOWS = [
    Workflow(
        id="author",
        display_name="Author",
        description=(
            "Create new abilities and adversaries from a description."
        ),
        signature=DSPyCalderaFactoryClient,
        required_servers=["caldera_core"],
        optional_servers=["cti_pipeline"],
        accepted_capabilities=["cti"],
        # The signature tells the model not to run operations. caldera_core is
        # required and cti_pipeline is now offered, and between them they
        # expose all three of these, so without the scope that instruction is
        # the only thing standing between an authoring run and a live
        # operation. Authoring an adversary stays allowed; running one does not.
        denied_tools=[
            "core_create_operation",
            "core_add_link_to_operation",
            "cti_pipeline_run_operation",
        ],
        mlflow_experiment=_MLFLOW_EXPERIMENT,
        ui_component="author.vue",
        example_prompts=[
            "Create a few abilities related to persistence with WMI for Windows, then create an adversary with those abilities. Please create more than one ability.",
            "Build a Linux discovery adversary using ATT&CK T1057 and T1018 techniques.",
            "Author an adversary that exfiltrates data over DNS, with at least three supporting abilities.",
        ],
        run=run,
    ),
]
