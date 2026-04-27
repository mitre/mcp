import os
import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import sys
import mlflow
from app.utility.base_world import BaseWorld
import traceback
from mlflow.tracking import MlflowClient
import asyncio
from contextlib import AsyncExitStack

def _expand_env(value):
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value

def get_llm_config():
    try:
        config = BaseWorld.strip_yml('plugins/mcp/conf/default.yml')[0]
        return _expand_env(config.get('llm', {}))
    except Exception as e:
        print(f"[MCP] Failed to load LLM config: {e}")
        return {}

def build_lm_from_dict(settings: dict) -> dspy.LM:
    # Support offline mode if present
    if settings.get("offline", False):
        os.environ["LITELLM_MODEL_METADATA_LOCAL_PATH"] = "/path/to/local.json"

    # Get API key with proper None handling
    api_key = settings.get("api_key") or ""

    # Validate API key is provided
    if not api_key:
        raise ValueError("API key is required but not provided. Please set your API key in the Global Model Configuration.")

    lm_kwargs = {
        "model": settings.get("model") or "gpt-4o",
        "api_key": api_key,
        "api_base": settings.get("api_base"),
    }
    # Optional params if provided
    if settings.get("temperature") is not None:
        lm_kwargs["temperature"] = settings.get("temperature")
    if settings.get("max_tokens") is not None:
        lm_kwargs["max_tokens"] = settings.get("max_tokens")

    return dspy.LM(**lm_kwargs)

def get_env(lm_settings=None):
    env = os.environ.copy()
    venv_site_packages = os.path.join(sys.prefix, "Lib", "site-packages")
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{venv_site_packages}:{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = venv_site_packages

    # Pass LLM config to subprocess via environment variables
    if lm_settings:
        # Use 'or' to handle None values and ensure we always get strings
        env['DSPY_MODEL'] = str(lm_settings.get('model') or 'gpt-4o')
        env['DSPY_API_KEY'] = str(lm_settings.get('api_key') or '')
        env['DSPY_API_BASE'] = str(lm_settings.get('api_base') or '')
        env['DSPY_TEMPERATURE'] = str(lm_settings.get('temperature') or 0.5)
        env['DSPY_MAX_TOKENS'] = str(lm_settings.get('max_tokens') or 10000)

    # Forward Caldera credentials so each MCP server subprocess can hit the API
    env['CALDERA_URL'] = os.environ.get('CALDERA_URL', 'http://localhost:8888/api/v2/')
    env['CALDERA_API_KEY'] = os.environ.get('CALDERA_API_KEY', 'ADMIN123')

    return env

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("caldera-mcp-client-1")
mlflow.dspy.autolog()
current_dir = os.path.dirname(os.path.abspath(__file__))

class DSPyCalderaPlannerClient(dspy.Signature):
    """You are a planner for the Caldera adversary emulation platform.
    You have access to MCP tool servers that wrap Caldera's core API and any
    installed plugins. Your job is to PLAN and EXECUTE operations using
    existing abilities and adversaries.

    Prefer reusing existing artifacts over creating new ones. Use range or
    infrastructure tools only when the operation requires live targets.
    """
    adversary_emulation_task: str = dspy.InputField()
    process_result: str = dspy.OutputField(
        desc=(
            "Message that summarizes the result of the adversary emulation operation."
        )
    )

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
    """
    adversary_emulation_task: str = dspy.InputField()
    cti_context: str = dspy.InputField(
        desc="Relevant CTI (Cyber Threat Intelligence) information including attack patterns, techniques, and threat actor behaviors"
    )
    process_result: str = dspy.OutputField(
        desc=(
            "Message that summarizes the result of the adversary emulation operation, "
            "including how CTI information influenced the planning and execution."
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

async def run(adversary_emulation_task: str, lm_obj=None, rag_context=None, run_id=None, enabled_servers=None, server_registry=None):
    """
    lm_obj can be:
      - a dict with keys like model, api_key, api_base, temperature, max_tokens, offline
      - a dspy.LM instance
      - None, to fall back to config from default.yml
    """
    # Resolve LM configuration
    max_tool_calls = 5  # Default value
    if isinstance(lm_obj, dspy.LM):
        lm_instance = lm_obj
        lm_settings = None  # Can't extract settings from LM instance
    elif isinstance(lm_obj, dict):
        # Overlay GUI dict onto yaml; when yaml pins a gateway via api_base,
        # its model/api_base win over GUI submissions (gateway has constrained
        # model list, GUI default may not match).
        yaml_cfg = get_llm_config() or {}
        merged = {**yaml_cfg, **{k: v for k, v in lm_obj.items() if v not in (None, "")}}
        if yaml_cfg.get("api_base") and yaml_cfg.get("model"):
            merged["model"] = yaml_cfg["model"]
            merged["api_base"] = yaml_cfg["api_base"]
        lm_instance = build_lm_from_dict(merged)
        lm_settings = merged
        max_tool_calls = lm_obj.get("max_tool_calls") or 5
    else:
        cfg = get_llm_config()
        lm_instance = build_lm_from_dict(cfg)
        lm_settings = cfg
        max_tool_calls = cfg.get("max_tool_calls") or 5

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
        server_registry = {
            "caldera_core": {
                "path": os.path.join(current_dir, "mcp_server.py"),
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
                if rag_context:
                    signature = DSPyCalderaPlannerClientWithRAG
                    formatted_context = format_rag_context(rag_context)

                    # Log CTI context being sent to LLM for verification
                    mlflow.log_param("cti_context_preview", formatted_context[:1000])  # First 1000 chars
                    mlflow.set_tag("cti_context_length", len(formatted_context))
                    mlflow.set_tag("cti_search_results_count", len(rag_context.get("search_results", [])))
                    mlflow.set_tag("cti_detailed_context_count", len(rag_context.get("detailed_context", [])))
                    print(f"[MCP] Passing CTI context to LLM ({len(formatted_context)} chars)")

                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    mlflow.set_tag("stage", "executing DSPy ReAct with RAG")
                    result = await react.acall(
                        adversary_emulation_task=adversary_emulation_task,
                        cti_context=formatted_context
                    )
                else:
                    signature = DSPyCalderaPlannerClient
                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    mlflow.set_tag("stage", "executing DSPy ReAct")
                    result = await react.acall(
                        adversary_emulation_task=adversary_emulation_task
                    )

            mlflow.set_tag("stage", "completed")
            mlflow.set_tag("status", "complete")
            mlflow.set_tag("reasoning", result.reasoning)
            mlflow.set_tag("process_result", result.process_result)
            for k, v in result.trajectory.items():
                mlflow.set_tag(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v))

            mlflow.log_param("result_summary", result.process_result)
            mlflow.end_run()
            print(json.dumps(result.toDict(), indent=4))
            return {"process_result": result.process_result}

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
