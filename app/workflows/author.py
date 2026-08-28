import os
import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import sys
import mlflow
import traceback
from mlflow.tracking import MlflowClient
import asyncio
from contextlib import AsyncExitStack

from plugins.mcp.app.config import caldera_connection, llm_defaults, mlflow_settings
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
        env[ENV_TEMPERATURE] = str(lm_settings.get('temperature') or 0.5)
        env[ENV_MAX_TOKENS] = str(lm_settings.get('max_tokens') or 24000)
        if lm_settings.get('timeout') is not None:
            env[ENV_TIMEOUT] = str(lm_settings.get('timeout'))
        if lm_settings.get('ssl_verify') is not None:
            env[ENV_SSL_VERIFY] = str(lm_settings.get('ssl_verify')).lower()

    caldera = caldera_connection()
    env['CALDERA_URL'] = os.environ.get('CALDERA_URL') or caldera['url']
    env['CORE_CALDERA_API_KEY'] = os.environ.get('CORE_CALDERA_API_KEY') or caldera['api_key']

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

class DSPyCalderaFactoryClientWithRAG(dspy.Signature):
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
    cti_context: str = dspy.InputField(
        desc="Relevant CTI (Cyber Threat Intelligence) information including attack patterns, techniques, and threat actor behaviors"
    )
    process_result: str = dspy.OutputField(
        desc=(
            _AUTHOR_OUTPUT_DESC
            + " When CTI context shaped what you authored, briefly note "
            "which CTI elements drove which design choices, but keep that "
            "note secondary to the substantive results themselves."
        )
    )

# Factory function to create tool functions with proper closure
def create_tool_function(session, tool_name, tool_description):
    async def tool_function(**kwargs):
        mlflow.set_tag("stage", f"Tool.{tool_name}")
        result = await session.call_tool(tool_name, kwargs)
        return result
    tool_function.__doc__ = tool_description
    return tool_function

def format_rag_context(rag_context):
    """Format RAG context into a string for the DSPy signature."""
    if not rag_context:
        return "No CTI context available."
    
    formatted_parts = []
    
    # Add search results summary
    if "search_results" in rag_context:
        formatted_parts.append("Relevant CTI findings:")
        for i, result in enumerate(rag_context["search_results"][:3], 1):
            formatted_parts.append(f"{i}. {result}")
    
    # Add detailed context
    if "detailed_context" in rag_context:
        formatted_parts.append("\nDetailed CTI Information:")
        for ctx in rag_context["detailed_context"]:
            formatted_parts.append(f"\n{ctx['name']}:")
            formatted_parts.append(f"{ctx['description']}")
    
    return "\n".join(formatted_parts)

async def run(adversary_emulation_task: str, lm_obj=None, rag_context=None, run_id=None, enabled_servers=None, server_registry=None, cti_context: str = "", **_extra_capability_context):
    # cti_context (formatted string) is the new orchestrator's path. rag_context
    # (raw dict) is the legacy mcp_svc shim. Either may be supplied; cti_context
    # wins. **_extra_capability_context absorbs unknown kwargs from future
    # capabilities so adding one doesn't break this signature.
    #
    # lm_obj is the dict mcp_svc produces from resolve_llm_config (yaml + .env
    # + UI overrides, with fields_locked enforced). Workflows trust it; they
    # do not re-merge yaml here. Tests that call run() directly without
    # lm_obj fall back to the same yaml-resolved defaults.
    _ensure_mlflow()
    lm_settings = dict(lm_obj) if lm_obj else llm_defaults()
    max_tool_calls = lm_settings.get("max_tool_calls") or 5

    # Both credentials are checked here rather than at dspy.LM() so the
    # failure lands before the AsyncExitStack spawns MCP subprocesses.
    missing = next(
        (f for f in ("api_key", "api_base") if not lm_settings.get(f)), None
    )
    if missing:
        error_msg = f"{missing} is required but not provided. Please set it in the Global Model Configuration."
        print(f"[MCP] ERROR: {error_msg}")
        if not run_id:
            run = mlflow.start_run(run_name="MCP Ability Factory")
            run_id = run.info.run_id
        mlflow.set_tag("status", "failed")
        mlflow.set_tag("stage", "error")
        mlflow.log_param("error", error_msg)
        mlflow.log_param("prompt", adversary_emulation_task)
        mlflow.end_run()
        raise ValueError(error_msg)

    # Use the passed-in run_id to continue the MLflow run if provided
    created_local_run = False
    if not run_id:
        run = mlflow.start_run(run_name="MCP Ability Factory")
        run_id = run.info.run_id
        created_local_run = True

    mlflow.set_tag("status", "running")
    mlflow.set_tag("stage", "initializing")
    mlflow.log_param("prompt", adversary_emulation_task)

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

    mlflow.log_param("enabled_servers", ",".join(enabled_servers))

    # Bump max iters when non-core servers are in the mix (realistic runs need more)
    if any(name != "caldera_core" for name in enabled_servers) and max_tool_calls < 10:
        max_tool_calls = 10
    mlflow.log_param("max_tool_calls", max_tool_calls)

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
                mlflow.set_tag("stage", f"initializing MCP session: {server_name}")
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                sessions.append(session)

            # Merge tools across all sessions with collision detection
            mlflow.set_tag("stage", "listing tools")
            seen = {}
            dspy_tools = []
            for server_name, session in zip(enabled_servers, sessions):
                tool_list = (await session.list_tools()).tools
                for tool in tool_list:
                    if tool.name in seen:
                        raise ValueError(
                            f"Tool name collision: '{tool.name}' defined by both "
                            f"'{seen[tool.name]}' and '{server_name}'. "
                            f"Namespace tool names with a server prefix."
                        )
                    seen[tool.name] = server_name
                    dspy_tools.append(dspy.Tool.from_mcp_tool(session, tool))
            mlflow.log_param("tool_count", len(dspy_tools))

            # Use context to set LM for this task/run
            lm_kwargs = dspy_lm_kwargs_from_settings(lm_settings)
            with dspy.context(lm=dspy.LM(**lm_kwargs)):
                mlflow.set_tag("stage", "creating DSPy ReAct instance")

                # Resolve CTI context: prefer the orchestrator-supplied string,
                # fall back to formatting the legacy structured dict.
                resolved_cti = cti_context
                if not resolved_cti and rag_context:
                    resolved_cti = format_rag_context(rag_context)

                if resolved_cti:
                    signature = DSPyCalderaFactoryClientWithRAG
                    mlflow.log_param("cti_context_preview", resolved_cti[:1000])
                    mlflow.set_tag("cti_context_length", len(resolved_cti))
                    if rag_context:
                        mlflow.set_tag("cti_search_results_count", len(rag_context.get("search_results", [])))
                        mlflow.set_tag("cti_detailed_context_count", len(rag_context.get("detailed_context", [])))
                    print(f"[MCP] Passing CTI context to LLM ({len(resolved_cti)} chars)")

                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    mlflow.set_tag("stage", "executing DSPy ReAct with RAG")
                    result = await safe_react_acall(
                        react,
                        adversary_emulation_task=adversary_emulation_task,
                        cti_context=resolved_cti,
                    )
                else:
                    signature = DSPyCalderaFactoryClient
                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    mlflow.set_tag("stage", "executing DSPy ReAct")
                    result = await safe_react_acall(
                        react,
                        adversary_emulation_task=adversary_emulation_task,
                    )

            # Log outputs and trajectory. The live /status endpoint reads
            # from mcp_svc's in-memory run cache, not from MLflow; these
            # writes are observability for the MLflow UI and the History
            # tab (which still scrapes tags to reconstruct trajectories
            # for past runs that have aged out of the live cache).
            mlflow.set_tag("stage", "completed")
            mlflow.set_tag("status", "complete")
            mlflow.set_tag("reasoning", result.reasoning)
            mlflow.set_tag("process_result", result.process_result)

            for k, v in result.trajectory.items():
                mlflow.set_tag(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v))

            mlflow.log_param("result_summary", result.process_result)

            print(json.dumps(result.toDict(), indent=4))

            # End the run only if we created it locally
            if created_local_run:
                mlflow.end_run()

            return {
                "process_result": result.process_result,
                "reasoning": result.reasoning,
                "trajectory": dict(result.trajectory),
            }

    except Exception as e:
        tb = traceback.format_exc()
        print("[MCP] Exception occurred:")
        print(tb)
        mlflow.set_tag("status", "failed")
        mlflow.set_tag("stage", "error")
        mlflow.log_param("error", str(e))
        mlflow.log_param("traceback", tb)
        if created_local_run:
            mlflow.end_run()
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
        optional_servers=[],
        accepted_capabilities=["rag"],
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
