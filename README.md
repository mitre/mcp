# Caldera MCP Plugin

An AI-powered plugin for Caldera that orchestrates long-running LLM workflows to automatically create adversary emulation abilities and plan operations. Optionally enriches workflows with Retrieval-Augmented Generation (RAG) using Cyber Threat Intelligence (CTI) from STIX JSON files. All executions are tracked via MLflow for full observability into LLM reasoning and tool usage.

## Recent changes

- **`cti_pipeline` MCP server**: `mcp_server.py` now registers a dedicated `cti_pipeline` server exposing six tools the LLM can call in sequence — `cti_pipeline_ingest_cti`, `cti_pipeline_build_topology`, `cti_pipeline_synthesize_deploy_spec`, `cti_pipeline_deploy_range`, `cti_pipeline_run_operation`, `cti_pipeline_validate_detections`.
- **`plan_execute` rewritten as zero-to-hero**: raw CTI → STIX 2.1 → topology → deploy spec → infrastructure → agents → operation → detection scoring. The DSPy program enforces two non-negotiable directives: **GROUNDING** (every fact must come from a tool call — never invented) and **AGNOSTIC TO INPUT** (any CTI domain — ransomware, APT, ICS, insider, AI/ML, supply chain).
- **`ae-e2e` workflow card removed** from the landing page. The `AEEndToEndWorkflow` class is retained for the CLI client (`scripts/e2e_full_vision.sh`).
- **`Upload CTI` landing-page card restored** from the previous github/CTI era so STIX bundles can be staged before a run.
- **CTI extractor fidelity improvements**: against the CTID BlackCat plan eval — techniques recall 5.9% → 70.6%, services 0% → 42.9%, software 33% → 42%. All ontology-driven (NLTK / WordNet / IANA `/etc/services` / ATT&CK `x-mitre-data-source` SDOs / mimetypes); **no static lists** are used in the pipeline.
- **`cti_pipeline_deploy_range`** now auto-registers the synthesised profile via `POST /plugin/range/onprem/save-profile` before deploying, so LLM-generated profile names no longer trip the range plugin's profile validation.

## Features

- **LLM Ability Factory**: Generate custom Caldera abilities from natural language descriptions
- **LLM Operation Planner**: Create and execute complete adversary emulation operations
- **CTI Integration**: Enhance abilities with real-world threat intelligence from STIX bundles
- **MLflow Tracking**: Full observability of LLM reasoning, tool calls, and execution trajectory
- **Flexible Model Support**: Works with most LLM providers (OpenAI, Anthropic, etc.)
- **Run History**: Browse and search all historical executions with full details

## Quick Start

### 1. Start Caldera

From the Caldera root directory:

```bash
python3 server.py --insecure
```

The MCP plugin automatically starts MLflow on port 5000 during Caldera initialization.

### 2. Access the MCP Interface

Navigate to the Caldera web interface and select the **MCP** plugin from the sidebar.

### 3. Configure Your LLM

In the Global Model Configuration panel:
- Enter your **API key** (required)
- Select your **model** (default: gpt-4o)
- Adjust **temperature** and **max_tokens** as needed
- Set **max tool calls** for ReAct iterations (default: 5)

### 4. Choose Your Workflow

**LLM Ability Factory**: Create specific abilities
- Example: "Create a Windows ability that dumps credentials using PowerShell"

**LLM Operation Planner**: Plan and execute operations
- Example: "Execute a ransomware simulation on Windows agents"

### 5. Run Your Task

1. Enter your prompt in natural language
2. (Optional) Select STIX CTI files to enhance with threat intelligence
3. Click **Execute**
4. Watch real-time progress via MLflow stages and reasoning
5. View results and created abilities/operations

## Architecture

### Core Components

**Frontend (Vue.js)**
- `mcp.vue`: Main landing page with navigation
- `chat/ChatWorkflow.vue`: Chat-style session page used for every built-in
  workflow (Author, Plan and Execute); reads display_name, description,
  accepted_capabilities, and supports_chat_history off the workflow
  registration so a single component covers all workflows
- `chat/ChatSidebar.vue`, `ChatTranscript.vue`, `ChatMessage.vue`,
  `ChatComposer.vue`, `ChatThoughts.vue`, `ChatLoadingState.vue`: leaf
  components composed by ChatWorkflow
- `chat/composables/useMcpRun.js`, `useTrajectory.js`: reactive helpers
  for the run lifecycle and trajectory parsing
- `mcp_history.vue`: Historical run browser

**Backend (Python)**
- `mcp_api.py`: aiohttp API routes
- `mcp_svc.py`: Service orchestration layer
- `mcp_factory_client.py`: Ability factory DSPy client
- `mcp_planner_client.py`: Operation planner DSPy client
- `mcp_server.py`: MCP tool server exposing Caldera API
- `factory.py`: Command generation DSPy module
- `rag.py`: STIX CTI retrieval service

**Integration**
- `hook.py`: Plugin initialization and MLflow startup

## Configuration

### Default Settings

Edit `conf/default.yml` to set default LLM configuration:

```yaml
llm:
  model: gpt-4o
  api_key: YOUR_API_KEY
  offline: true
  use_mock: false
factory:
  model: gpt-4o
  api_key: YOUR_API_KEY
  temperature: 0.4
```

**Note**: Frontend model configuration overrides these defaults per run.

### RAG Configuration

When using CTI enhancement:
- **Embedding Model**: Default `openai/text-embedding-3-small`
- **Top-K Retrieval**: Default 5 objects (configurable via UI)
- **STIX File Location**: Upload files via UI, stored in `data/` directory

## Using CTI Integration

### Upload STIX Files

1. Navigate to **MCP → Ability Factory** or **Planner**
2. In the RAG Configuration section, click **Upload STIX File**
3. Select your STIX JSON bundle(s)
4. Files are stored in `plugins/mcp/data/`

### Enable CTI for a Run

1. In the RAG Configuration panel, select which STIX files to use
2. (Optional) Adjust embedding model and top-K retrieval
3. Execute your task normally

The LLM will receive relevant CTI context based on your prompt, including:
- Attack patterns and techniques
- Malware and tool descriptions
- Threat actor TTPs
- Campaign information

### CTI Data Flow

```
User Prompt → RAG Search (Semantic) → Top-K CTI Objects Retrieved
                                    ↓
                        Detailed Context for Top 3 Objects
                                    ↓
                        Formatted CTI Context String
                                    ↓
                        LLM Receives Task + CTI Context
                                    ↓
                        Creates CTI-Informed Abilities/Operations
```

## MLflow Tracking

### Access MLflow UI

Open your browser to: **http://localhost:5000**

Navigate to **Experiments → Traces** to view:
- Run status and stages
- LLM chain of thought (`thought_0`, `thought_1`, etc.)
- Tool calls and arguments (`tool_name_N`, `tool_args_N`)
- RAG retrieval steps (when CTI is used)
- Final results and reasoning

### Understanding Run Tags

**Status Tags**:
- `status`: running, complete, failed
- `stage`: Current execution phase
- `reasoning`: LLM's final reasoning summary
- `process_result`: Summary of what was created

**RAG Tags** (when CTI is enabled):
- `rag_retrieval_step_N`: RAG retrieval process
- `rag_retrieved_object_N`: Names of CTI objects retrieved
- `cti_context_preview`: First 1000 chars of CTI sent to LLM
- `cti_context_length`: Total CTI context size

**LLM Trajectory**:
- `thought_N`: LLM reasoning at each step
- `observation_N`: Tool execution results
- `tool_name_N`: Tool that was called
- `tool_args_N`: Arguments passed to tool

## Extending the Framework

See the **Extend & Customize** guide in the UI for detailed instructions on:
- Creating custom DSPy clients
- Adding new MCP tools
- Building custom workflows
- Integrating with the service layer

Example use cases:
- Threat Hunter: Analyze adversary profiles and generate detection rules
- Operation Optimizer: Review completed operations and suggest improvements
- Campaign Builder: Create multi-stage campaigns from threat actor profiles

## Development

### Testing Individual Components

```bash
# Test factory client (requires running Caldera)
cd app
python mcp_factory_client.py

# Test planner client
python mcp_planner_client.py

# Test MCP server tools
python mcp_server.py
```

### Project Structure

```
plugins/mcp/
├── app/                    # Python backend
│   ├── mcp_api.py         # API routes
│   ├── mcp_svc.py         # Service layer
│   ├── mcp_factory_client.py
│   ├── mcp_planner_client.py
│   ├── mcp_server.py      # MCP tool server
│   ├── factory.py         # Command generation
│   └── rag.py             # CTI retrieval
├── gui/views/             # Vue frontend
│   ├── mcp.vue
│   ├── chat/              # chat-style workflow session page
│   │   ├── ChatWorkflow.vue
│   │   ├── ChatSidebar.vue
│   │   ├── ChatTranscript.vue
│   │   ├── ChatMessage.vue
│   │   ├── ChatComposer.vue
│   │   ├── ChatThoughts.vue
│   │   ├── ChatLoadingState.vue
│   │   └── composables/{useMcpRun,useTrajectory}.js
│   └── mcp_history.vue
├── conf/default.yml       # Default configuration
├── data/                  # STIX JSON files
├── hook.py                # Plugin initialization
└── README.md
```

## Dependencies

- **dspy**: LLM orchestration framework with ReAct pattern
- **mcp**: Model Context Protocol SDK for tool servers
- **mlflow**: Experiment tracking and tracing
- **aiohttp**: Async web framework
- **psutil**: Process management for MLflow server
- **requests**: HTTP client for Caldera API

## Troubleshooting

### API Key Errors

**Error**: "API key is required but not provided"

**Solution**: Enter your API key in the Global Model Configuration panel before executing.

### MLflow Not Starting

**Error**: Cannot access http://localhost:5000

**Solution**: Check Caldera logs for MLflow startup messages. The plugin automatically kills processes on port 5000 and starts MLflow during initialization.

### RAG Retrieval Failures

**Error**: "RAG service not initialized" or embedding errors

**Solution**:
- Verify STIX files are valid JSON
- Ensure API key has access to embedding models
- Check MLflow logs for detailed error messages

### Tool Execution Failures

**Error**: Tools fail to initialize or execute

**Solution**:
- Verify Caldera API is accessible at `http://localhost:8888/api/v2/`
- Check MCP server subprocess logs for environment issues
- Ensure PYTHONPATH includes venv packages

### Viewing Detailed Logs

Check MLflow UI for:
1. Full trajectory of tool calls
2. Error messages in `error` param
3. Traceback in `traceback` param
4. Stage where failure occurred

## Support

For bugs and feature requests:
- Check MLflow traces for detailed execution information
- Review Caldera logs with `[MCP]` prefix
- Consult the in-app Extension Guide for development questions

## License

Part of the Caldera project. See main Caldera repository for license information.
