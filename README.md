# Caldera MCP Plugin

CALDERA MCP adds an AI-assisted operations workspace to CALDERA. It gives operators chat-based workflows for creating adversary content, ingesting CTI, selecting generated STIX, and planning adversary-emulation runs.

The plugin is designed to keep the LLM grounded in MCP tools and server-side context instead of asking the operator to manually stitch together CTI, CALDERA state, and operation planning details.

<p align="center">
  <img src="docs/images/mcp-main-screen.png" alt="Caldera MCP main screen" width="900">
</p>

<br>

<p align="center"><em>Main MCP workspace with workflow cards and global model configuration.</em></p>

<br>

## Features

- **Author workflow**: Create CALDERA abilities and adversaries from an operator prompt while using available MCP server tools.
- **Plan and Execute workflow**: Select or upload CTI/STIX, build an adversary from the observed techniques, run the CALDERA operation against available agents, and report which techniques it covered.
- **CTI ingest pipeline**: Upload raw CTI in HTML, PDF, plaintext, or Markdown and produce STIX 2.1 bundles for retrieval and planning.
- **STIX selection for planning**: Pick generated STIX bundles from the Plan and Execute workspace. Selecting STIX automatically enables CTI retrieval for that run.
- **Model and CTI/RAG profiles**: Configure the chat model, API base, API key, temperature, token budget, and tool-call budget. CTI/RAG can use the chat model by default or a saved profile when it needs a different endpoint.
- **MCP server discovery**: Expose CALDERA core tools and optional plugin servers, including the CTI pipeline when installed.
- **Run history and transcripts**: Keep chat sessions, tool calls, reasoning summaries, and final artifacts available for review.

## Recent Changes

### Plan and Execute Workspace

Plan and Execute now has a dedicated workspace for CTI-driven adversary emulation. The workflow keeps its prompt context centralized, and shows the LLM endpoint controls in the session.

<p align="center">
  <img src="docs/images/mcp-plan-execute-workspace.png" alt="MCP Plan and Execute workspace" width="900">
</p>

<br>

<p align="center"><em>Plan and Execute workspace with LLM endpoint and CTI/RAG controls.</em></p>

<br>

### STIX Selection Modal

The Plan and Execute CTI picker is now a graphical modal that lists generated STIX bundles with model, provider, and size metadata. The selected bundles are summarized under the CTI section in the workflow sidebar.

<p align="center">
  <img src="docs/images/mcp-plan-execute-stix-selector.png" alt="MCP Plan and Execute STIX selector" width="900">
</p>

<br>

<p align="center"><em>Graphical STIX selection modal used by Plan and Execute.</em></p>

<br>

### CTI Ingest Pipeline

The CTI ingest workflow stages raw CTI files, runs extraction, and displays generated STIX bundles for later use by RAG-enabled workflows. The generated STIX output is what Plan and Execute uses to build adversaries and seed operations.

<p align="center">
  <img src="docs/images/mcp-cti-ingest-pipeline.png" alt="MCP CTI ingest pipeline screen" width="900">
</p>

<br>

<p align="center"><em>CTI ingest pipeline for raw reports and generated STIX bundles.</em></p>

<br>

### What the pipeline produces

A threat report tells you **what** to run. Your environment tells you **where**.

The pipeline extracts ATT&CK techniques, the named threat actor, and file
hash observables, and nothing else. It does not extract hosts, accounts, domains, services or
software, and does not turn them into CALDERA facts. Those describe the
report's victim, not your estate; CALDERA discovers facts about your hosts
at runtime, which is why the abilities that use them carry `has_agent_copy`
and `no_backwards_movement` requirements.

The one insertion point into core CALDERA is the adversary profile:

```
upload report(s) -> clean -> IR -> ATT&CK techniques -> STIX bundle
                                                            |
  "build an adversary from this and run it"                 v
      build_adversary   attack-pattern -> ability.technique_id -> Adversary
                        + unmatched_techniques + platform_excluded
      run_operation     Adversary + your agents + runtime-discovered facts
```

### Known limits

- **Extraction quality.** Scored against the committed measuring stick with
  `tests/test_pipeline_score.py`: precision 0.83, F1 0.89. That fixture names
  its technique ids explicitly, so its recall is an upper bound, not a field
  estimate. Recall on prose-only reports is materially lower, and fusing
  several reports on the same actor is the cheapest way to raise it.
- **No detection scoring.** The `detections` plugin does not ship in this
  repository, so nothing here scores an operation against SIEM rules.
- **Platform matching is coarse.** `build_adversary` knows which platforms
  your agents run, not whether a Windows agent is domain-joined. It reports
  the gap in `platform_excluded` rather than closing it.
- **Fusion does not check identity.** Fusing bundles for two different
  actors merges them into one profile without complaint.
- **Operations are not agent-scoped.** `run_operation` runs against the whole
  `red` group; the `agent_paws` argument is not honoured by core's operation
  schema.

## Installation

Install MCP like a standard CALDERA plugin.

1. Clone or copy this repository into the CALDERA plugin directory:

```bash
git clone https://github.com/mitre/mcp.git plugins/mcp
```

2. Add `mcp` to your CALDERA plugin list in `conf/local.yml`. Keep local configuration in `conf/local.yml`; do not commit that file.

```yaml
plugins:
  - magma
  - sandcat
  - stockpile
  - mcp
```

3. Install plugin requirements from the CALDERA virtual environment:

```bash
source venv/bin/activate
pip install -r plugins/mcp/requirements.txt
```

4. Install the spaCy model. pip cannot do this from `requirements.txt`:

```bash
python -m spacy download en_core_web_lg
```

   Install poppler as well, which supplies `pdftotext`. Without it the
   pipeline still ingests TXT, MD and HTML, and PDF uploads report the
   missing dependency rather than failing silently:

```bash
brew install poppler          # macOS
apt install poppler-utils     # Debian/Ubuntu
```

   To run the test suite, also install the dev requirements:

```bash
pip install -r plugins/mcp/requirements-dev.txt
```

5. Copy `.env.example` to `.env` and set the LLM endpoint and credential.
   Both are optional: with neither set, IR extraction falls back to a
   deterministic offline extractor. That extractor trades roughly 15 to 20
   percent of recall for sub-second processing, so configure a model when
   extraction quality matters.

```bash
cp plugins/mcp/.env.example plugins/mcp/.env
```

| Variable | Purpose |
|---|---|
| `MCP_LLM_API_BASE` | OpenAI-compatible API root, for example `https://api.openai.com/v1`. An unresolved value is refused rather than defaulting to public OpenAI. |
| `MCP_LLM_API_KEY` | Key for whichever provider `MCP_LLM_API_BASE` points at. Optional only if every request supplies its own through the UI. |

Both may instead be supplied per-session through the UI's Global Model Configuration. Avoid committing secrets.

Nothing needs setting for the Caldera connection. The plugin builds the REST URL from the host and port CALDERA binds to, and picks the API key CALDERA's own `api_key_red` or `api_key_blue` accepts. Set `CALDERA_URL` only when MCP runs somewhere that cannot reach the address CALDERA binds to, such as a separate container or host; running behind the `ssl` plugin is not such a case, since haproxy forwards to the same local address. Set `CORE_CALDERA_API_KEY` on any server whose `conf/local.yml` was generated. A rejected key is reported on the plugin's splash page and in the CALDERA log at startup.

## Quick Start

1. Start CALDERA from the repository root:

```bash
source venv/bin/activate
python server.py --insecure --log=DEBUG
```

2. If MCP UI code changed, start CALDERA with the build flag so Magma rebuilds plugin UI assets:

```bash
source venv/bin/activate
python server.py --insecure --log=DEBUG --build
```

3. Open CALDERA in the browser and select **mcp** from the sidebar.

4. In **Global Model Config**, choose or create an endpoint profile. The default model field is `openai/gpt-oss-120b`; set API base, API key, temperature, tool-call budget, and token budget for your environment.

5. Use **Upload CTI** to ingest raw reports and generate STIX, or start **Plan and Execute** and select existing STIX bundles from the CTI sidebar.

6. For Plan and Execute, if no CTI is selected, the workflow runs without CTI retrieval. If STIX is selected, CTI retrieval is enabled automatically.

## Workflow Guide

### Author

Use Author when you want CALDERA content from a natural-language request. The workflow can call available MCP tools to create or update abilities and adversaries.

### Upload CTI

Use Upload CTI to stage raw reports, run CTI extraction, and produce STIX 2.1 bundles. Generated bundles are stored by the plugin and can be selected later from Plan and Execute.

### Plan and Execute

Use Plan and Execute for CTI-driven operations. The workflow can:

- Read selected STIX bundles and CTI/RAG context.
- Fuse several bundles describing the same actor into one.
- Build an adversary from the observed techniques, previewing it first.
- Run the CALDERA operation against agents that have checked in.
- Report which techniques had no matching ability, and which had one that
  no live agent can run.

The CTI names techniques, not your estate. The workflow reports a gap
rather than answering a question about your environment from a report.

## Configuration

### Model Profiles

MCP supports saved endpoint profiles in the UI. Profiles can carry:

- Model name
- API base
- API key
- Temperature
- Maximum tool calls
- Maximum tokens

CTI and RAG share the chat endpoint. Extraction differs from chat only in its generation settings, which the CTI Extraction Model panel edits.

### Local Settings

Prefer environment variables for local values, and keep `conf/default.yml` limited to safe defaults.

To pin values on disk instead, create `conf/local.yml`. That file is a **sparse overlay**, not a full config: it is deep-merged onto `conf/default.yml` key by key, so it needs only the keys it changes. A file containing one key is valid and complete.

```yaml
llm:
  model: openai/gpt-oss-120b
  api_base: https://api.example.com/v1
  offline: false

cti:
  timeout: 120
  offline: false
```

Three rules that are easy to trip over:

- **`cti` layers over `llm`, but only for its own generation settings.** A workload profile may set `top_p`, `timeout`, `stream`, `offline` and `embed_model`. Everything else belongs to `llm`: the connection (`provider`, `model`, `api_base`, credentials, `ssl_verify`), and `temperature` and `max_tokens`, which two panels display and so are stored once. Anything else under `cti` is dropped and logged, and `set_config` rejects it outright.
- **Precedence differs by field.** `api_key` resolves environment-first and is never read from this file. `api_base` resolves yaml-first, so a value here beats `MCP_LLM_API_BASE`; leave it empty to keep using the variable.
- **A key with no value is `null`, and null overrides.** A bare `llm:` heading wipes the shipped block rather than falling through to it. Omit the block instead.

The GUI's **Global Model Config** panel writes the connection to the `llm` profile in `conf/local.yml`, so it configures every workload including CTI extraction. Only fields you change are written, so a value still coming from `MCP_LLM_API_BASE` is left alone rather than pinned to disk. The API key is the exception: it stays in `localStorage` and rides each request, and `set_config` strips credentials before writing.

## API Surface

The plugin exposes MCP workflow APIs through CALDERA's aiohttp server. The UI uses those APIs to:

- Start workflow sessions.
- Send chat prompts.
- List MCP servers and tools.
- Save and load endpoint profiles.
- Upload raw CTI.
- List generated STIX bundles.
- Run CTI pipeline steps.
- Read run history and transcripts.

The CTI pipeline MCP server exposes five tools: `cti_pipeline_ingest_cti`,
`cti_pipeline_fuse`, `cti_pipeline_build_adversary`,
`cti_pipeline_run_operation` and `cti_pipeline_wait_for_agents`.

When adding new UI functionality, prefer extending the existing MCP API routes instead of creating separate side channels.

## Architecture

### Reasoning stack

The agent loop is a DSPy [ReAct](https://dspy.ai/) program: signatures define each
workflow's persona and I/O contract, LiteLLM carries completions to the configured
OpenAI-compatible endpoint. Three layers support it:

| Layer | Role |
|---|---|
| **MCP servers** | The API and tool-calling surface. Every action the agent can take is an MCP tool, so reasoning stays grounded in real CALDERA and plugin state. |
| **RAG** | Context augmentation. This is where CTI enters the prompt — selected STIX bundles are retrieved and injected as `cti_context` before the loop starts. |
| **MLflow** | Observability for thoughts and reasoning. Each run's trajectory, tool calls, and final artifacts are logged for later review. |

### Plugin discovery

The MCP plugin is a host for other plugins' capabilities rather than a fixed
tool set. At CALDERA boot it scans every installed plugin for an `mcp_server.py`,
spawns the ones a workflow enables as stdio subprocesses, and merges their tools
into that workflow's ReAct loop. A plugin contributes tools, and optionally
workflows, capabilities, and Vue UI — without the MCP plugin being modified.

```text
CALDERA core
  +-- MCP plugin ---> discovers MCP servers ---> operations / adversaries / abilities
  +-- Plugin N ------> MCP server ------------> API endpoints with Swagger docs
                              |
                              +-- tools + API routes for context and tool calls
                              +-- powering the ReAct / DSPy reasoning loop
```

Because discovery is per-plugin and opt-in, the tool surface a given run sees is
exactly the set of servers that workflow declared and the operator enabled.
See [PLUGIN_MCP.md](PLUGIN_MCP.md) for the full contribution contract.

## Project Structure

```text
plugins/mcp/
+-- app/
|   +-- mcp_api.py                 # aiohttp routes used by the UI
|   +-- mcp_svc.py                 # service orchestration
|   +-- mcp_gui.py                 # UI route registration
|   +-- mcp_server.py              # in-process MCP server tools
|   +-- capabilities/
|   |   +-- rag.py                 # STIX retrieval support
|   +-- workflows/
|   |   +-- author.py              # Author workflow
|   |   +-- plan_execute.py        # Plan and Execute workflow
|   |   +-- prompts/               # centralized prompt context
|   +-- utilities/
|       +-- cti_*                  # CTI extraction, validation, enrichment
+-- conf/
|   +-- default.yml                # safe defaults only
+-- docs/
|   +-- images/                    # README screenshots
+-- gui/views/
|   +-- mcp.vue                    # landing page
|   +-- cti.vue                    # CTI ingest workflow
|   +-- chat/                      # chat workflow components
+-- mcp_server.py                  # standalone MCP entrypoint
+-- requirements.txt
+-- tests/                         # pytest suite
+-- hook.py                        # plugin initialization
```

## Development

Run tests from the plugin repository when available:

```bash
pytest tests
```

Useful CALDERA startup commands from the CALDERA root:

```bash
source venv/bin/activate
python server.py --insecure --log=DEBUG
python server.py --insecure --log=DEBUG --build
```

Use `--build` after changing Vue, CSS, or other Magma-loaded UI assets.

## Troubleshooting

- **MCP page does not appear**: Confirm `mcp` is listed in `conf/local.yml` and restart CALDERA.
- **UI changes are missing**: Restart with `--build` so Magma rebuilds plugin UI bundles.
- **Model calls fail**: Check the endpoint profile, API base, API key, and model name. The API base often needs a `/v1` suffix for OpenAI-compatible servers.
- **Caldera tools return 401 or the splash reports a rejected key**: CALDERA hashes its API keys at startup, so a generated `conf/local.yml` has a key the plugin cannot guess. Set `CORE_CALDERA_API_KEY` in `plugins/mcp/.env` to the `API_TOKEN` printed once in the CALDERA log when that file was created.
- **CTI/RAG does not run**: Select at least one generated STIX bundle in Plan and Execute. CTI selection automatically enables RAG for that workflow.
- **Deploy spec has review gaps**: The CTI did not provide enough grounded evidence. Add richer CTI, select more STIX bundles, or review the gaps before deployment.

## License

This plugin follows the licensing terms of the CALDERA project and its plugin ecosystem.
