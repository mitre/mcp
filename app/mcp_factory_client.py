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

def get_llm_config():
    try:
        config = BaseWorld.strip_yml('plugins/mcp/conf/default.yml')[0]
        return config.get('llm', {})
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

    if lm_settings:
        env['DSPY_MODEL'] = str(lm_settings.get('model') or 'gpt-4o')
        env['DSPY_API_KEY'] = str(lm_settings.get('api_key') or '')
        env['DSPY_TEMPERATURE'] = str(lm_settings.get('temperature') or 0.5)
        env['DSPY_MAX_TOKENS'] = str(lm_settings.get('max_tokens') or 10000)
        env['DSPY_API_BASE'] = str(lm_settings.get('api_base') or '')  # FIXED

    return env

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("caldera-mcp-FACTORY-client-1")

current_dir = os.path.dirname(os.path.abspath(__file__))

class DSPyCalderaFactoryClient(dspy.Signature):
    """You are an ability factory for the Caldera adversary emulation platform.  You are given a list of tools to handle user requests and control Caldera via the
    MCP server for the Caldera API.  You will be given a user request and you will need to decide the right tools to use and use them accordingly
    to fulfill the user request.
    """

    adversary_emulation_task: str = dspy.InputField()
    process_result: str = dspy.OutputField(
        desc=(
            "Message that summarizes the result of the newly created adversary."
        )
    )

class DSPyCalderaFactoryClientWithRAG(dspy.Signature):
    """You are an ability factory for the Caldera adversary emulation platform enhanced with Cyber Threat Intelligence (CTI) data.
    You are given a list of tools to handle user requests and control Caldera via the MCP server for the Caldera API.
    You also have access to CTI context that provides information about attack patterns, malware, tools, threat actors, and techniques.
    Use the CTI context to create more accurate and realistic adversary emulations based on real-world threat intelligence.
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

def create_tool_function(session, tool_name, tool_description):
    async def tool_function(**kwargs):
        mlflow.set_tag("stage", f"Tool.{tool_name}")
        result = await session.call_tool(tool_name, kwargs)
        return result
    tool_function.__doc__ = tool_description
    return tool_function

def format_rag_context(rag_context):
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

async def run(adversary_emulation_task: str, lm_obj = None, rag_context=None, run_id=None):
    lm_settings = {}
    max_tool_calls = 5
    if lm_obj:
        lm_obj_safe = copy.deepcopy(lm_obj) or {}
        lm_settings = {
            "model": lm_obj_safe.get("model") or "gpt-4o",
            "api_key": lm_obj_safe.get("api_key") or "",
            "api_base": lm_obj_safe.get("api_base") or "",  # FIXED
            "temperature": lm_obj_safe.get("temperature") or 0.5,
            "max_tokens": lm_obj_safe.get("max_tokens") or 10000,
        }
        max_tool_calls = lm_obj_safe.get("max_tool_calls") or 5
    else:
        llm_config = get_llm_config()
        lm_settings = {
            "model": llm_config.get("model") or "gpt-4o",
            "api_key": llm_config.get("api_key") or "",
            "api_base": llm_config.get("api_base") or "",  # FIXED
            "temperature": llm_config.get("temperature") or 0.5,
            "max_tokens": llm_config.get("max_tokens") or 10000,
        }
        max_tool_calls = llm_config.get("max_tool_calls") or 5

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

    created_local_run = False
    if not run_id:
        run = mlflow.start_run(run_name="MCP Ability Factory")
        run_id = run.info.run_id
        created_local_run = True

    mlflow.set_tag("status", "running")
    mlflow.set_tag("stage", "initializing")
    mlflow.log_param("prompt", adversary_emulation_task)

    server_params = StdioServerParameters(
        command="python",
        args=[current_dir+"/mcp_server.py"],
        env=get_env(lm_settings),
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                mlflow.set_tag("stage", "initializing MCP session")
                await session.initialize()

                mlflow.set_tag("stage", "listing tools")
                tools = await session.list_tools()

                with dspy.context(lm=dspy.LM(
                    f"nvidia_nim/" + lm_settings['model'],
                    api_key=lm_settings['api_key'],
                    api_base=lm_settings['api_base'],
                    temperature=lm_settings['temperature'],
                    max_tokens=lm_settings['max_tokens']
                )):
                    mlflow.set_tag("stage", "creating DSPy ReAct instance")
                    dspy_tools = [dspy.Tool.from_mcp_tool(session, tool) for tool in tools.tools]

                    if rag_context:
                        signature = DSPyCalderaFactoryClientWithRAG
                        formatted_context = format_rag_context(rag_context)

                        mlflow.log_param("cti_context_preview", formatted_context[:1000])
                        mlflow.set_tag("cti_context_length", len(formatted_context))
                        mlflow.set_tag("cti_search_results_count", len(rag_context.get("search_results", [])))
                        mlflow.set_tag("cti_detailed_context_count", len(rag_context.get("detailed_context", [])))
                        print(f"[MCP] Passing CTI context to LLM ({len(formatted_context)} chars)")

                        react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                        mlflow.set_tag("stage", "executing DSPy ReAct with RAG")
                        result = await react.acall(adversary_emulation_task=adversary_emulation_task, cti_context=formatted_context)
                    else:
                        signature = DSPyCalderaFactoryClient
                        react = dspy.ReAct(signature, tools=dspy_tools, max_iters=max_tool_calls)
                        mlflow.set_tag("stage", "executing DSPy ReAct")
                        result = await react.acall(adversary_emulation_task=adversary_emulation_task)

                mlflow.set_tag("stage", "completed")
                mlflow.set_tag("status", "complete")
                mlflow.set_tag("reasoning", result.reasoning)
                mlflow.log_param("process_result", result.process_result)
                mlflow.set_tag("process_result", result.process_result)

                for k, v in result.trajectory.items():
                    mlflow.set_tag(k, json.dumps(v) if isinstance(v, (dict, list)) else str(v))

                mlflow.log_param("result_summary", result.process_result)

                print(json.dumps(result.toDict(), indent=4))

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