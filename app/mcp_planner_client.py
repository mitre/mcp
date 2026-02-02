import os
import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json
import sys
import mlflow
import traceback
import asyncio
from plugins.mcp.app.utilities.llm_client import load_config, init_mlflow

def build_lm_from_dict(settings: dict) -> dspy.LM:
    # Support offline mode if present
    if settings.get("offline", False):
        os.environ["LITELLM_MODEL_METADATA_LOCAL_PATH"] = "/path/to/local.json"

    # Get API key with proper None handling
    api_key = settings.get("api_key") or ""

    # Validate API key is provided
    if not api_key:
        raise ValueError("API key is required but not provided. Please set your API key in the Global Model Configuration.")
    api_base = settings.get("api_base")
    if not api_base:
        raise ValueError("api_base is required for openai-compatible models")
    lm_kwargs = {
        "model": settings.get("model") or "gpt-4o",
        "api_key": api_key,
        "api_base": api_base,
        "provider": settings.get("provider"),
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
        env['DSPY_TEMPERATURE'] = str(lm_settings.get('temperature') or 0.5)
        env['DSPY_MAX_TOKENS'] = str(lm_settings.get('max_tokens') or 10000)

    return env

current_dir = os.path.dirname(os.path.abspath(__file__))

class DSPyCalderaPlannerClient(dspy.Signature):
    """You are a planner for the Caldera adversary emulation platform.  You are given a list of tools to handle user requests and control Caldera via the
    MCP server for the Caldera API.  You will be given a user request and you will need to decide the right tools to use and use them accordinly
    to fulfill the user request and conduct an adversary emulation operation.
    """

    adversary_emulation_task: str = dspy.InputField()
    process_result: str = dspy.OutputField(
        desc=(
            "Message that summarizes the result of the adversary emulation operation."
        )
    )

class DSPyCalderaPlannerClientWithRAG(dspy.Signature):
    """You are a planner for the Caldera adversary emulation platform enhanced with Cyber Threat Intelligence (CTI) data.
    You are given a list of tools to handle user requests and control Caldera via the MCP server for the Caldera API.
    You also have access to CTI context that provides information about attack patterns, malware, tools, threat actors, and techniques.
    Use the CTI context to plan more realistic and comprehensive adversary emulation operations based on real-world threat intelligence.
    When planning operations, consider the attack patterns and techniques used by real threat actors to create more authentic scenarios.
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

async def run(adversary_emulation_task: str, lm_obj=None, rag_context=None, run_id=None):
    """
    lm_obj can be:
      - a dict with keys like model, api_key, api_base, temperature, max_tokens, offline
      - a dspy.LM instance
      - None, to fall back to config from default.yml
    """
    init_mlflow(profile="planner")
    # Resolve LM configuration
    max_tool_calls = 5  # Default value
    if isinstance(lm_obj, dspy.LM):
        lm_instance = lm_obj
        lm_settings = None  # Can't extract settings from LM instance
    elif isinstance(lm_obj, dict):
        lm_instance = build_lm_from_dict(lm_obj)
        lm_settings = lm_obj
        max_tool_calls = lm_obj.get("max_tool_calls") or 5
    else:
        cfg = load_config()
        llm_config = cfg.get("planner") or cfg.get("llm", {})
        lm_instance = build_lm_from_dict(llm_config)
        lm_settings = llm_config
        max_tool_calls = llm_config.get("max_tool_calls") or 5

    # Start or resume MLflow run
    if run_id:
        # Attach to existing run WITHOUT starting a new one
        mlflow.set_tag("planner_attached", "true")
    else:
        run = mlflow.start_run(run_name="MCP Planner Run")
        run_id = run.info.run_id

    mlflow.set_tag("status", "running")
    mlflow.set_tag("stage", "initializing")
    mlflow.log_param("prompt", adversary_emulation_task)

    # Create server params with LLM settings passed via environment
    server_params = StdioServerParameters(
        command="python",
        args=[current_dir+"/mcp_server.py"],
        env=get_env(lm_settings),
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("[MCP] Initializing MCP session...")
                mlflow.set_tag("stage", "initializing MCP session")
                await session.initialize()

                mlflow.set_tag("stage", "listing tools")
                tools = await session.list_tools()

                dspy_tools = [dspy.Tool.from_mcp_tool(session, tool) for tool in tools.tools]

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
                parsed = None
                try:
                    parsed = PydanticModel.model_validate_json(result.process_result)
                except Exception:
                    # Log but do not fail the run
                    mlflow.set_tag("output_format", "unstructured")

                mlflow.set_tag("stage", "completed")
                mlflow.set_tag("status", "complete")
                if hasattr(result, "reasoning"):
                    mlflow.set_tag("reasoning", result.reasoning)

                mlflow.set_tag("process_result", result.process_result)
                for k, v in result.trajectory.items():
                    mlflow.set_tag(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v))

                mlflow.log_param("result_summary", result.process_result)
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
        