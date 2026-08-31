# Caldera MCP Plugin

An AI-assisted operations workspace for CALDERA. Chat-driven workflows create adversary content, ingest CTI into STIX, and plan and run adversary emulation, with the LLM grounded in MCP tools and live CALDERA state instead of operator copy-paste.

![Caldera MCP main screen](docs/images/mcp-main-screen.png)

## Workflows

| Workflow | What it does |
|---|---|
| **Author** | Creates or updates CALDERA abilities and adversaries from a natural-language prompt. |
| **Upload CTI** | Ingests HTML, PDF, TXT or Markdown reports and produces STIX 2.1 bundles. |
| **Plan and Execute** | Selects STIX bundles, fuses reports on one actor, builds an adversary from the observed techniques, runs the operation, and reports coverage gaps. |

Selecting STIX in Plan and Execute enables CTI retrieval for that run; with none selected the workflow runs without it. Every run keeps its transcript, tool calls and artifacts for review.

## What the pipeline produces

A threat report tells you **what** to run. Your environment tells you **where**.

Extraction yields ATT&CK techniques, the named threat actor and file hash observables, and nothing else. Hosts, accounts, domains, services and software describe the report's victim rather than your estate, so they never become CALDERA facts. CALDERA discovers those at runtime, which is why the abilities that use them carry `has_agent_copy` and `no_backwards_movement` requirements.

The one insertion point into core CALDERA is the adversary profile:

```text
upload report(s) -> clean -> IR -> ATT&CK techniques -> STIX bundle
                                                            |
  "build an adversary from this and run it"                 v
      build_adversary   attack-pattern -> ability.technique_id -> Adversary
                        + unmatched_techniques + platform_excluded
      run_operation     Adversary + your agents + runtime-discovered facts
```

## Installation

Install like any CALDERA plugin, from the CALDERA root:

```bash
git clone https://github.com/mitre/mcp.git plugins/mcp
source venv/bin/activate
pip install -r plugins/mcp/requirements.txt
python -m spacy download en_core_web_lg
cp plugins/mcp/.env.example plugins/mcp/.env
```

The spaCy model needs its own command because pip cannot install it from `requirements.txt`. Then add `mcp` to the `plugins:` list in `conf/local.yml`, alongside `magma`, `sandcat` and `stockpile`. Do not commit that file.

Optional extras:

```bash
brew install poppler                              # macOS, supplies pdftotext
apt install poppler-utils                         # Debian/Ubuntu
pip install -r plugins/mcp/requirements-dev.txt   # to run the test suite
```

Without poppler, TXT, MD and HTML still ingest and PDF uploads report the missing dependency rather than failing silently.

### LLM credentials

| Variable | Purpose |
|---|---|
| `MCP_LLM_API_BASE` | OpenAI-compatible API root, for example `https://api.openai.com/v1`. An unresolved value is refused rather than defaulting to public OpenAI. |
| `MCP_LLM_API_KEY` | Key for whatever `MCP_LLM_API_BASE` points at. Optional if every request supplies its own through the UI. |

Both are optional, and both can instead be supplied per session through the UI's Global Model Configuration. With neither set, IR extraction falls back to a deterministic offline extractor that trades roughly 15 to 20 percent of recall for sub-second processing, so configure a model when extraction quality matters.

### Caldera connection

Nothing needs setting. The plugin builds the REST URL from the host and port CALDERA binds to, and picks whichever of `api_key_red` or `api_key_blue` CALDERA accepts. Two exceptions:

- `CALDERA_URL`, only when MCP runs somewhere that cannot reach that address, such as a separate container or host. Running behind the `ssl` plugin is not such a case, since haproxy forwards to the same local address.
- `CORE_CALDERA_API_KEY`, on any server whose `conf/local.yml` was generated. CALDERA hashes its keys at startup, so the plugin cannot guess a generated one; use the `API_TOKEN` printed once in the log when that file was created. A rejected key is reported on the splash page and in the log at startup.

## Quick start

```bash
source venv/bin/activate
python server.py --insecure --log=DEBUG
```

Add `--build` whenever Vue, CSS or other Magma-loaded UI assets changed, so Magma rebuilds the plugin bundles.

Open CALDERA, select **mcp** in the sidebar, then choose or create an endpoint profile in **Global Model Config** (the default model field is `openai/gpt-oss-120b`). From there, use **Upload CTI** to generate STIX, or **Plan and Execute** to select existing bundles and run.

Tests run with `pytest tests` from the plugin directory.

## Configuration

**Global Model Config** writes the connection to the `llm` profile in `conf/local.yml`, so it configures every workload including CTI extraction. Only fields you change are written, so a value still coming from `MCP_LLM_API_BASE` is left alone rather than pinned to disk. The API key is the exception: it stays in `localStorage` and rides each request, and `set_config` strips credentials before writing.

To pin values on disk directly, write `conf/local.yml` by hand. It is a **sparse overlay**, not a full config: it is deep-merged onto `conf/default.yml` key by key, so it needs only the keys it changes.

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

- **`cti` layers over `llm`, but only for its own generation settings:** `top_p`, `timeout`, `stream`, `offline` and `embed_model`. Everything else belongs to `llm`, including the connection (`provider`, `model`, `api_base`, credentials, `ssl_verify`) and `temperature` and `max_tokens`, which two panels display and so are stored once. Anything else under `cti` is dropped and logged, and `set_config` rejects it outright.
- **Precedence differs by field.** `api_key` resolves environment-first and is never read from this file. `api_base` resolves yaml-first, so a value here beats `MCP_LLM_API_BASE`; leave it empty to keep using the variable.
- **A key with no value is `null`, and null overrides.** A bare `llm:` heading wipes the shipped block rather than falling through to it. Omit the block instead.

## Architecture

The agent loop is a DSPy [ReAct](https://dspy.ai/) program: signatures define each workflow's persona and I/O contract, and LiteLLM carries completions to the configured OpenAI-compatible endpoint. Three layers support it:

| Layer | Role |
|---|---|
| **MCP servers** | The API and tool-calling surface. Every action the agent can take is an MCP tool, so reasoning stays grounded in real CALDERA and plugin state. |
| **RAG** | Context augmentation. Selected STIX bundles are retrieved and injected as `cti_context` before the loop starts. |
| **MLflow** | Observability for thoughts and reasoning. Each run's trajectory, tool calls and final artifacts are logged for review. |

The plugin is a host for other plugins' capabilities rather than a fixed tool set. At CALDERA boot it scans every installed plugin for an `mcp_server.py`, spawns the ones a workflow enables as stdio subprocesses, and merges their tools into that workflow's ReAct loop. A plugin can contribute tools, and optionally workflows, capabilities and Vue UI, without MCP being modified. Because discovery is per-plugin and opt-in, the tool surface a run sees is exactly the servers that workflow declared and the operator enabled. See [PLUGIN_MCP.md](PLUGIN_MCP.md) for the full contribution contract.

The CTI pipeline server exposes five tools: `cti_pipeline_ingest_cti`, `cti_pipeline_fuse`, `cti_pipeline_build_adversary`, `cti_pipeline_run_operation` and `cti_pipeline_wait_for_agents`. New UI functionality should extend the existing MCP API routes instead of creating separate side channels.

## Troubleshooting

| Symptom | Fix |
|---|---|
| MCP page does not appear | Confirm `mcp` is listed in `conf/local.yml` and restart CALDERA. |
| UI changes are missing | Restart with `--build`. |
| Model calls fail | Check the endpoint profile, API base, key and model name. The API base often needs a `/v1` suffix. |
| Caldera tools return 401, or the splash reports a rejected key | Set `CORE_CALDERA_API_KEY`. See [Caldera connection](#caldera-connection). |
| CTI/RAG does not run | Select at least one generated STIX bundle in Plan and Execute. |
| Deploy spec has review gaps | The CTI did not provide enough grounded evidence. Add richer reports, select more bundles, or review the gaps before deploying. |

## License

This plugin follows the licensing terms of the CALDERA project and its plugin ecosystem.
