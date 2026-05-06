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

from plugins.mcp.app.config import llm_defaults
from plugins.mcp.app.dspy_env import (
    ENV_API_BASE,
    ENV_API_KEY,
    ENV_MAX_TOKENS,
    ENV_MODEL,
    ENV_TEMPERATURE,
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

    lm_kwargs = {
        "model": settings.get("model") or "gpt-4o",
        "api_key": api_key,
        "api_base": settings.get("api_base"),
    }
    if settings.get("temperature") is not None:
        lm_kwargs["temperature"] = settings.get("temperature")
    if settings.get("max_tokens") is not None:
        lm_kwargs["max_tokens"] = settings.get("max_tokens")
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
        env[ENV_TEMPERATURE] = str(lm_settings.get('temperature') or 0.5)
        env[ENV_MAX_TOKENS] = str(lm_settings.get('max_tokens') or 10000)

    env['CALDERA_URL'] = os.environ.get('CALDERA_URL', 'http://localhost:8888/api/v2/')
    env['CORE_CALDERA_API_KEY'] = os.environ.get('CORE_CALDERA_API_KEY', 'ADMIN123')

    return env

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("caldera-mcp-client-1")
mlflow.dspy.autolog()
current_dir = os.path.dirname(os.path.abspath(__file__))

_PLAN_EXECUTE_OUTPUT_DESC = (
    "The substantive answer to the user's request. Include the actual data "
    "observed from your tool calls: counts, names, ids, statuses, and any "
    "values the user asked about. When listing things, use a short bulleted "
    "or numbered list with the real names from the observations, not "
    "placeholders. Do NOT narrate which tools you called or describe your "
    "methodology. Do NOT say things like 'I first listed X, then I retrieved "
    "Y'. The user wants the results, not a recap of how you got them. "
    "If a tool failed and you could not retrieve some data, say so clearly "
    "and name what is missing, but still return whatever data you did get."
)


_CHAT_HISTORY_DESC = (
    "Prior turns in this chat session, oldest first. Each turn is "
    "labelled 'User:' / 'Assistant:'. Use them to resolve follow-up "
    "references like 'that profile', 'the instance I just created', "
    "or 'add it to the deployment from earlier'. The current request "
    "still arrives in adversary_emulation_task; chat_history is "
    "context for interpreting it. Empty string on the first turn."
)


class DSPyCalderaPlannerClient(dspy.Signature):
    """You are a planner for the Caldera adversary emulation platform.
    You have access to MCP tool servers that wrap Caldera's core API and any
    installed plugins. Your job is to PLAN and EXECUTE operations using
    existing abilities and adversaries.

    Prefer reusing existing artifacts over creating new ones. Use range or
    infrastructure tools only when the operation requires live targets.

    When chat_history is non-empty, treat it as the conversation so far and
    interpret the current request in that context. Reuse entity ids that
    appeared in earlier turns rather than asking the user to repeat them.

    When you produce process_result, return the substantive content the
    user asked for (real names, counts, ids, statuses), not a recap of the
    tools you called.
    """
    adversary_emulation_task: str = dspy.InputField()
    chat_history: str = dspy.InputField(default="", desc=_CHAT_HISTORY_DESC)
    process_result: str = dspy.OutputField(desc=_PLAN_EXECUTE_OUTPUT_DESC)

class DSPyCalderaPlannerClientWithRAG(dspy.Signature):
    """You are a planner for the Caldera adversary emulation platform,
    enhanced with Cyber Threat Intelligence (CTI) data. You have access to MCP
    tool servers that wrap Caldera's core API and any installed plugins. Your
    job is to PLAN and EXECUTE operations informed by CTI, using existing
    abilities and adversaries.

    Prefer reusing existing artifacts over creating new ones. Use range or
    infrastructure tools only when the operation requires live targets.
    Ground your plan in the provided CTI context so the operation mirrors
    real-world threat actor behavior.

    When chat_history is non-empty, treat it as the conversation so far and
    interpret the current request in that context. Reuse entity ids that
    appeared in earlier turns rather than asking the user to repeat them.

    When you produce process_result, return the substantive content the
    user asked for (real names, counts, ids, statuses), not a recap of the
    tools you called.
    """
    adversary_emulation_task: str = dspy.InputField()
    cti_context: str = dspy.InputField(
        desc="Relevant CTI (Cyber Threat Intelligence) information including attack patterns, techniques, and threat actor behaviors"
    )
    chat_history: str = dspy.InputField(default="", desc=_CHAT_HISTORY_DESC)
    process_result: str = dspy.OutputField(
        desc=(
            _PLAN_EXECUTE_OUTPUT_DESC
            + " When CTI context shaped the plan, briefly note which "
            "CTI elements drove which decisions, but keep that note "
            "secondary to the substantive results themselves."
        )
    )

# Factory function to create tool functions with proper closure
def create_tool_function(session, tool_name, tool_description):
    async def tool_function(**kwargs):
        result = await session.call_tool(tool_name, kwargs)
        return result
    tool_function.__doc__ = tool_description
    return tool_function

def format_rag_context(rag_context):
    """Format RAG context into a string for the DSPy signature."""
    if not rag_context:
        return "No CTI context available."
    formatted_parts = []
    if "search_results" in rag_context:
        formatted_parts.append("Relevant CTI findings:")
        for i, result in enumerate(rag_context["search_results"][:3], 1):
            formatted_parts.append(f"{i}. {result}")
    if "detailed_context" in rag_context:
        formatted_parts.append("\nDetailed CTI Information:")
        for ctx in rag_context["detailed_context"]:
            formatted_parts.append(f"\n{ctx['name']}:")
            formatted_parts.append(f"{ctx['description']}")
    return "\n".join(formatted_parts)

async def run(adversary_emulation_task: str, lm_obj=None, rag_context=None, run_id=None, enabled_servers=None, server_registry=None, cti_context: str = "", chat_history: str = "", **_extra_capability_context):
    """
    lm_obj can be:
      - a dict produced by mcp_svc.resolve_llm_config (yaml + .env + UI
        overrides already merged, with fields_locked enforced)
      - a dspy.LM instance (kept for backwards compatibility with callers
        that build their own LM)
      - None, to fall back to llm_defaults() from the shared config module
        (used by tests / direct invocation)
    """
    if isinstance(lm_obj, dspy.LM):
        lm_instance = lm_obj
        lm_settings = None
        max_tool_calls = 5
    else:
        lm_settings = dict(lm_obj) if isinstance(lm_obj, dict) else llm_defaults()
        lm_instance = _build_lm_from_settings(lm_settings)
        max_tool_calls = lm_settings.get("max_tool_calls") or 5

    # Start or resume MLflow run
    if run_id:
        mlflow.end_run()  # Ensure no active run
        mlflow.start_run(run_id=run_id)
    else:
        run = mlflow.start_run(run_name="MCP Planner Run")
        run_id = run.info.run_id

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
                    command="python",
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

            # Use per-call LM context, honoring lm_obj if provided
            with dspy.context(lm=lm_instance):
                mlflow.set_tag("stage", "creating DSPy ReAct instance")
                # Resolve CTI context: prefer the orchestrator-supplied string,
                # fall back to formatting the legacy structured dict.
                resolved_cti = cti_context
                if not resolved_cti and rag_context:
                    resolved_cti = format_rag_context(rag_context)

                if resolved_cti:
                    signature = DSPyCalderaPlannerClientWithRAG
                    mlflow.log_param("cti_context_preview", resolved_cti[:1000])
                    mlflow.set_tag("cti_context_length", len(resolved_cti))
                    if rag_context:
                        mlflow.set_tag("cti_search_results_count", len(rag_context.get("search_results", [])))
                        mlflow.set_tag("cti_detailed_context_count", len(rag_context.get("detailed_context", [])))
                    print(f"[MCP] Passing CTI context to LLM ({len(resolved_cti)} chars)")

                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    mlflow.set_tag("stage", "executing DSPy ReAct with RAG")
                    result = await react.acall(
                        adversary_emulation_task=adversary_emulation_task,
                        cti_context=resolved_cti,
                        chat_history=chat_history,
                    )
                else:
                    signature = DSPyCalderaPlannerClient
                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    mlflow.set_tag("stage", "executing DSPy ReAct")
                    result = await react.acall(
                        adversary_emulation_task=adversary_emulation_task,
                        chat_history=chat_history,
                    )

            if chat_history:
                mlflow.set_tag("chat_history_length", len(chat_history))

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
            mlflow.end_run()
            print(json.dumps(result.toDict(), indent=4))
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
        mlflow.end_run()
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
        description=(
            "Plan and execute operations using existing abilities, adversaries, "
            "and infrastructure. With CTI ingestion enabled, can also provision "
            "infrastructure that matches the environment described in the report."
        ),
        signature=DSPyCalderaPlannerClient,
        required_servers=["caldera_core"],
        optional_servers=["range"],
        accepted_capabilities=["rag"],
        ui_component="plan_execute.vue",
        example_prompts=[
            "Plan an emulation against the Discovery adversary on my available agents.",
            "Build infrastructure that resembles the environment described in the attached CTI report.",
            "Stand up a small ICS testbed with two Windows hosts and one Linux jumpbox, then run a discovery operation against it.",
        ],
        run=run,
        supports_chat_history=True,
    ),
]
