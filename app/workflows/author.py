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
import copy
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

def configure_llm(llm_config, use_mock=False):
    if use_mock:
        class MockLM:
            def __call__(self, prompt):
                return "Mocked response"
        dspy.configure(lm=MockLM())
        return

    if llm_config.get("offline", False):
        os.environ["LITELLM_MODEL_METADATA_LOCAL_PATH"] = "/path/to/local.json"

    lm = {
        "model": llm_config.get("model", "gpt-4o"),
        "api_key": llm_config.get("api_key", ""),
        "api_base": llm_config.get("api_base")
    }
    
    dspy.configure(lm=lm)

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
mlflow.set_experiment("caldera-mcp-FACTORY-client-1")
mlflow.dspy.autolog()

current_dir = os.path.dirname(os.path.abspath(__file__))

class DSPyCalderaFactoryClient(dspy.Signature):
    """You are an ability factory for the Caldera adversary emulation platform.
    You have access to MCP tool servers that wrap Caldera's core API and any
    installed plugins. Your job is to AUTHOR reusable artifacts: abilities and
    adversaries. Do NOT run operations or deploy infrastructure.

    Use only the tools needed to create the requested artifact. If a tool
    deploys VMs, runs operations, or performs destructive actions, do not
    call it unless the user's request explicitly requires it.
    """

    adversary_emulation_task: str = dspy.InputField()
    process_result: str = dspy.OutputField(
        desc=(
            "Message that summarizes the result of the newly created adversary."
        )
    )

class DSPyCalderaFactoryClientWithRAG(dspy.Signature):
    """You are an ability factory for the Caldera adversary emulation platform,
    enhanced with Cyber Threat Intelligence (CTI) data. You have access to MCP
    tool servers that wrap Caldera's core API and any installed plugins. Your
    job is to AUTHOR reusable artifacts: abilities and adversaries informed by
    CTI. Do NOT run operations or deploy infrastructure.

    Use only the tools needed to create the requested artifact. If a tool
    deploys VMs, runs operations, or performs destructive actions, do not
    call it unless the user's request explicitly requires it.
    """

    adversary_emulation_task: str = dspy.InputField()
    cti_context: str = dspy.InputField(
        desc="Relevant CTI (Cyber Threat Intelligence) information including attack patterns, techniques, and threat actor behaviors"
    )
    process_result: str = dspy.OutputField(
        desc=(
            "Message that summarizes the result of the newly created adversary, "
            "including how CTI information was used to enhance the adversary profile."
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
    # Build LM settings safely (support defaults)
    lm_settings = {}
    max_tool_calls = 5  # Default value
    if lm_obj:
        lm_obj_safe = copy.deepcopy(lm_obj) or {}
        yaml_cfg = get_llm_config()
        # When yaml configures an alternate gateway (api_base set), the yaml model
        # is authoritative — the gateway only accepts a constrained model list.
        if yaml_cfg.get("api_base") and yaml_cfg.get("model"):
            resolved_model = yaml_cfg["model"]
        else:
            resolved_model = lm_obj_safe.get("model") or yaml_cfg.get("model") or "gpt-4o"
        lm_settings = {
            "model": resolved_model,
            "api_key": lm_obj_safe.get("api_key") or yaml_cfg.get("api_key") or "",
            "api_base": lm_obj_safe.get("api_base") or yaml_cfg.get("api_base") or "",
            "temperature": lm_obj_safe.get("temperature") or 0.5,
            "max_tokens": lm_obj_safe.get("max_tokens") or 10000,
        }
        max_tool_calls = lm_obj_safe.get("max_tool_calls") or 5
    else:
        llm_config = get_llm_config()
        lm_settings = {
            "model": llm_config.get("model") or "gpt-4o",
            "api_key": llm_config.get("api_key") or "",
            "api_base": llm_config.get("api_base") or "",
            "temperature": llm_config.get("temperature") or 0.5,
            "max_tokens": llm_config.get("max_tokens") or 10000,
        }
        max_tool_calls = llm_config.get("max_tool_calls") or 5

    # Validate API key is provided
    if not lm_settings.get("api_key"):
        error_msg = "API key is required but not provided. Please set your API key in the Global Model Configuration."
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

            # Use context to set LM for this task/run
            lm_kwargs = {
                "api_key": lm_settings['api_key'],
                "temperature": lm_settings['temperature'],
                "max_tokens": lm_settings['max_tokens'],
            }
            if lm_settings.get('api_base'):
                lm_kwargs['api_base'] = lm_settings['api_base']
            with dspy.context(lm=dspy.LM(lm_settings['model'], **lm_kwargs)):
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
                    result = await react.acall(adversary_emulation_task=adversary_emulation_task, cti_context=resolved_cti)
                else:
                    signature = DSPyCalderaFactoryClient
                    react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                    mlflow.set_tag("stage", "executing DSPy ReAct")
                    result = await react.acall(adversary_emulation_task=adversary_emulation_task)

            # Log outputs and trajectory
            mlflow.set_tag("stage", "completed")
            mlflow.set_tag("status", "complete")
            mlflow.set_tag("reasoning", result.reasoning)
            # Prefer param for process_result to match status API
            mlflow.log_param("process_result", result.process_result)
            # Keep tag for backward compatibility (optional)
            mlflow.set_tag("process_result", result.process_result)

            for k, v in result.trajectory.items():
                mlflow.set_tag(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v))

            mlflow.log_param("result_summary", result.process_result)

            print(json.dumps(result.toDict(), indent=4))

            # End the run only if we created it locally
            if created_local_run:
                mlflow.end_run()

            return {"process_result": result.process_result}

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
            "Create new abilities and adversaries from a description. "
            "Best for authoring reusable artifacts; does not run operations or "
            "deploy infrastructure."
        ),
        signature=DSPyCalderaFactoryClient,
        required_servers=["caldera_core"],
        optional_servers=[],
        accepted_capabilities=["rag"],
        ui_component="author.vue",
        example_prompts=[
            "Create a few abilities related to persistence with WMI for Windows, then create an adversary with those abilities. Please create more than one ability.",
            "Build a Linux discovery adversary using ATT&CK T1057 and T1018 techniques.",
            "Author an adversary that exfiltrates data over DNS, with at least three supporting abilities.",
        ],
        run=run,
    ),
]