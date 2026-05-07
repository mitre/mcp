# Contributing an MCP Server (and more) from a Caldera Plugin

This document is the contract a Caldera plugin must follow if it wants
to surface its capabilities through the MCP plugin: tools the LLM can
call, optional workflows / capabilities / plan validators, and Vue UI
components.

The MCP plugin discovers contributions at boot. **You don't modify the
MCP plugin itself.** Drop the right files in your own plugin tree,
restart Caldera, and the MCP plugin's runtime picks them up.

---

## 1. What you can contribute

| Contribution | Required file | What it gets you |
|---|---|---|
| **MCP server** (tools the agent can call) | `<plugin>/mcp_server.py` | Your APIs become callable tools in any workflow whose `optional_servers` (or `required_servers`) include your plugin name |
| **Workflow** (a new agent persona) | `<plugin>/mcp/workflows.py` | A new card on the MCP home page bound to your DSPy signature |
| **Capability** (context modifier) | `<plugin>/mcp/capabilities.py` | A new toggle in workflow settings that injects extra context into the agent prompt |
| **Plan validator** (deterministic tool-call binder) | `<plugin>/mcp/translator.py` | Two-phase plan-then-execute support for workflows with `plan_validator` set |
| **Vue UI components** | `<plugin>/gui/views/*.vue` | Custom session pages or settings panels referenced by your workflow / capability |

Every contribution is independent. A plugin can ship a server only, a
workflow only, a capability only, all of them, or none. The MCP plugin
treats absence as opt-out.

---

## 2. Plugin layout

```
plugins/<your_plugin>/
├── hook.py                    # Caldera plugin entry, unchanged
├── mcp_server.py              # ← MCP server entrypoint (Caldera convention: at root)
├── mcp/                       # ← everything else MCP-related lives here
│   ├── __init__.py
│   ├── tools/                 # @mcp.tool() implementations
│   │   ├── __init__.py
│   │   ├── inventory.py
│   │   ├── deploy.py
│   │   └── …
│   ├── workflows.py           # WORKFLOWS = [Workflow(...)]   (optional)
│   ├── capabilities.py        # CAPABILITIES = [Capability(...)] (optional)
│   └── translator.py          # validate_plan(plan, services)   (optional)
└── gui/views/
    ├── my_workflow.vue        # Vue session page (optional)
    └── my_settings.vue        # Capability settings panel (optional)
```

The asymmetry — `mcp_server.py` at the plugin root, everything else under
`mcp/` — is deliberate. `mcp_server.py` at root is the long-standing
Caldera convention discovery scans for. The rest of the contract is new
and grouped under `mcp/` to keep the root tidy.

---

## 3. MCP Server contract

### 3.1 The entrypoint file

**Path:** `plugins/<your_plugin>/mcp_server.py`

Required at the top of the file:

```python
import os
from mcp.server.fastmcp import FastMCP

MCP_METADATA = {
    "display_name": "My Plugin",          # shown on workflow server checklists
    "default_enabled": False,             # whether to tick on by default
    "description": "Wraps the Foo API",   # one-liner
}

mcp = FastMCP("My Plugin MCP Server")
```

The `MCP_METADATA` dict is parsed by AST without executing your file
([app/discovery/servers.py:9](app/discovery/servers.py#L9)). It must be a
literal — strings, bools, ints — so discovery can read it without the
side effects of importing the module. Missing or unparseable
`MCP_METADATA` falls back to defaults (display name = plugin directory
name, `default_enabled=False`).

### 3.2 Defining tools

Use the `@mcp.tool()` decorator from FastMCP. Each function becomes a
tool the agent can call. Tool names **must be prefixed with your plugin
name** to avoid collisions across servers — the orchestrator raises if
two servers expose the same tool name:

```python
@mcp.tool(name="myplugin_list_things")
def list_things():
    """One-line description; the agent reads this to decide whether to call you."""
    return foo_api.list_things()

@mcp.tool(name="myplugin_create_thing")
def create_thing(name: str, count: int = 1):
    """Args become the tool's JSON schema. Type-annotate everything."""
    return foo_api.create(name=name, count=count)
```

The docstring is what the model sees. Keep it factual, action-oriented,
and short — no flavor text, no example dialogues.

### 3.3 Subprocess environment contract

Your `mcp_server.py` runs as a **stdio subprocess** spawned by the
workflow. The parent forwards a known set of environment variables; you
can rely on them and should not reach for anything else.

Forwarded by the parent (see
[app/workflows/author.py](app/workflows/author.py) `get_env()`):

| Env var | Meaning |
|---|---|
| `CALDERA_URL` | Base URL of the Caldera REST API (`http://localhost:8888/api/v2/` for local dev) |
| `CORE_CALDERA_API_KEY` | Admin key for Caldera REST (`ADMIN123` default) |
| `DSPY_MODEL`, `DSPY_API_KEY`, `DSPY_API_BASE`, `DSPY_TEMPERATURE`, `DSPY_MAX_TOKENS` | LLM credentials, only if your tools call back into DSPy (e.g. for command synthesis) |
| `PYTHONPATH` | Includes the venv's `site-packages` |

**Do not** call `dotenv.load_dotenv()` inside the subprocess. The parent
loads `.env` once at plugin enable; the subprocess inherits the
environment. Re-loading masks parent overrides.

If your server needs DSPy itself (rare — only when your tools generate
content with the LLM), import the lazy bootstrap from the MCP plugin's
namespace:

```python
# only if your tools need to use DSPy signatures internally
from dspy_env import ensure_lm_configured  # sibling import: app/ is on sys.path
```

### 3.4 Tools that talk back to Caldera

Standard pattern: build a small client wrapping the Caldera key, then
call it from your tools. Mirror what
[app/mcp_server.py](app/mcp_server.py) does:

```python
import requests

class CalderaClient:
    def __init__(self):
        self.url = os.environ.get("CALDERA_URL", "http://localhost:8888/api/v2/")
        self.headers = {
            "KEY": os.environ.get("CORE_CALDERA_API_KEY", "ADMIN123"),
            "Content-Type": "application/json",
        }
    def get(self, endpoint):
        r = requests.get(f"{self.url}{endpoint}", headers=self.headers)
        return r.json() if r.status_code == 200 else {"error": r.text}

caldera = CalderaClient()

@mcp.tool(name="myplugin_get_relevant")
def get_relevant():
    return caldera.get("…")
```

### 3.5 Running standalone

Your `mcp_server.py` must be runnable directly. The framework spawns it
with:

```
python plugins/<your_plugin>/mcp_server.py
```

Standard FastMCP boilerplate at the bottom of the file:

```python
if __name__ == "__main__":
    mcp.run()
```

### 3.6 Tool naming rules

| Rule | Example |
|---|---|
| Prefix every tool with your plugin name | `myplugin_list_things` |
| Use snake_case | `myplugin_create_user`, not `myplugin_createUser` |
| Be specific about the verb | `myplugin_get_inventory` (not `myplugin_inventory`) |
| One tool, one purpose | Don't conflate "get and create" in one tool |

Collisions across servers fail fast at run start with a clear error
([app/workflows/author.py](app/workflows/author.py) tool-merge loop) —
you'll see it immediately during your first integration test.

---

## 4. Workflow contract (optional)

A workflow is a new card on the MCP home page bound to a DSPy signature.

### 4.1 The file

**Path:** `plugins/<your_plugin>/mcp/workflows.py`

Must expose a module-level `WORKFLOWS = [Workflow(...), ...]`.

```python
import dspy
from plugins.mcp.app.workflows.base import Workflow


class MyPersona(dspy.Signature):
    """One paragraph instructing the agent. This becomes the system prompt."""
    user_intent: str = dspy.InputField()
    cti_context: str = dspy.InputField(
        desc="Optional CTI context",
        default="",
    )
    process_result: str = dspy.OutputField(
        desc="The substantive answer."
    )


async def run(user_intent, lm_obj, *, run_id=None,
              enabled_servers=None, server_registry=None,
              cti_context: str = "", **_extra):
    """Driver that builds a dspy.ReAct, calls it, returns the result.

    The framework hands you:
      - lm_obj: the resolved LLM config dict from mcp_svc.resolve_llm_config
      - enabled_servers / server_registry: which MCP servers to spawn
      - cti_context (or other capability fields): from any enabled capabilities
    Return a dict with at least {process_result, reasoning, trajectory}.
    """
    ...
    return {
        "process_result": result.process_result,
        "reasoning": result.reasoning,
        "trajectory": dict(result.trajectory),
    }


WORKFLOWS = [
    Workflow(
        id="my_workflow",
        display_name="My Workflow",
        description="One-line summary shown on the home page card.",
        signature=MyPersona,
        required_servers=["caldera_core"],
        optional_servers=["myplugin"],
        accepted_capabilities=["rag"],
        ui_component="my_workflow.vue",
        example_prompts=[
            "Do X with the Y context",
        ],
        run=run,
    ),
]
```

### 4.2 The `Workflow` dataclass

Defined in [app/workflows/base.py](app/workflows/base.py). Required and
optional fields:

| Field | Required | Notes |
|---|---|---|
| `id` | ✅ | Stable identifier used in API payloads, MLflow params, UI routing. Pick something namespaced like `myplugin_provision`. |
| `display_name` | ✅ | User-facing label on the home-page card. |
| `description` | ✅ | One or two sentences. |
| `signature` | ✅ | A `dspy.Signature` class. Input fields capabilities contribute to (e.g. `cti_context`) need a `default=""`. |
| `required_servers` | ✅ | MCP server names that must be present. If any are missing the workflow is hidden from `/plugin/mcp/workflows` entirely. |
| `optional_servers` | – | User-toggleable in the per-workflow checklist. Filtered to discovered servers. |
| `accepted_capabilities` | – | Capability ids the workflow can consume. |
| `plan_validator` | – | Dotted path to a function that validates structured plan output. See §6. |
| `ui_component` | – | Path to a Vue component, relative to your `gui/views/`. Empty falls back to a generic shell. |
| `example_prompts` | – | Suggestions under the prompt input. |
| `run` | ✅ | Async entry point. See §4.3. |

### 4.3 The `run()` function

Signature:

```python
async def run(prompt: str, lm_obj: dict, *,
              run_id: str | None = None,
              enabled_servers: list[str] | None = None,
              server_registry: dict | None = None,
              **capability_fields) -> dict:
    ...
```

What you receive:

| Arg | What it is |
|---|---|
| `prompt` | The user's input string. |
| `lm_obj` | A dict shaped `{model, api_key, api_base, temperature, max_tokens, max_tool_calls}`. Already resolved through `mcp_svc.resolve_llm_config`. Use it to build a `dspy.LM`. |
| `run_id` | The MLflow run id the orchestrator already opened. Use it to nest your logs. |
| `enabled_servers` | List of MCP server names to spawn (already filtered to your `required ∪ optional` and to actually-discovered servers). |
| `server_registry` | `{name: {path, metadata}}` for all discovered servers. Use the `path` to spawn the subprocess. |
| `**capability_fields` | Extra kwargs from enabled capabilities. The RAG capability contributes `cti_context`; future capabilities will contribute differently. Always accept `**_extra` so a future capability adding a new field doesn't break you. |

What you must return:

```python
{
    "process_result": "...",       # the answer string the UI renders in the Result panel
    "reasoning": "...",            # the agent's reasoning chain
    "trajectory": {                # DSPy ReAct trajectory dict
        "thought_0": "...",
        "tool_name_0": "...",
        "tool_args_0": {...},
        "observation_0": "...",
        ...
    },
}
```

The orchestrator reads these into the in-memory run cache; the live
`/plugin/mcp/status` endpoint surfaces them to the UI.

### 4.4 Reusing the framework's helpers

Don't reinvent these. Import from the MCP plugin's namespace:

```python
from plugins.mcp.app.config import llm_defaults, resolve_llm_config
from plugins.mcp.app.dspy_env import (
    ENV_API_BASE, ENV_API_KEY, ENV_MAX_TOKENS, ENV_MODEL, ENV_TEMPERATURE,
)
```

The `ENV_*` constants are the wire-format names the parent sets and the
subprocess reads. Use them in your `get_env()` helper if you write one.

---

## 5. Capability contract (optional)

A capability is a context modifier that runs before the workflow's
agent loop and contributes additional input fields.

### 5.1 The file

**Path:** `plugins/<your_plugin>/mcp/capabilities.py`

Must expose `CAPABILITIES = [Capability(...), ...]`.

```python
from plugins.mcp.app.capabilities.base import Capability


async def enrich(prompt: str, settings: dict) -> dict:
    """Run before the agent loop. Return dict whose keys match the
    workflow signature's input fields."""
    extra = await fetch_relevant_context(prompt, settings)
    return {"my_field": extra}


CAPABILITIES = [
    Capability(
        id="myplugin_attack_lookup",
        display_name="ATT&CK Lookup",
        description="Inject relevant ATT&CK techniques as context.",
        enrich=enrich,
        ui_settings_component="my_attack_settings.vue",
        contributes_fields=["my_field"],
    ),
]
```

### 5.2 The wiring rule

Capability output reaches a workflow only when **all three** are true:

1. The workflow's `accepted_capabilities` includes the capability's id.
2. The user has enabled the capability for this run.
3. The workflow's signature has an `InputField` whose name matches one
   of the capability's `contributes_fields`.

If any of those is false, the field is silently dropped. The framework
warns at registration if (1) and (3) disagree to catch drift early.

### 5.3 What `enrich()` receives

| Arg | What it is |
|---|---|
| `prompt` | The user's input string for this run. |
| `settings` | A dict of per-capability user settings. The framework auto-injects an `api_key` derived from the resolved LLM key for capabilities that need an embedding model. Other settings come from the capability's UI panel (`ui_settings_component`). |

Return a dict — keys become signature input fields. Empty dict means
"no contribution this run."

---

## 6. Plan validator contract (optional)

For workflows with `plan_validator` set, the framework treats the
agent's structured output as a plan and hands it to a deterministic
validator that returns the actual tool-call sequence to execute.

### 6.1 The file

**Path:** `plugins/<your_plugin>/mcp/translator.py`

Exposes a single function the workflow references via dotted path:

```python
async def validate_plan(plan, *, services) -> tuple[bool, str, list[dict]]:
    """Validate a structured plan against this plugin's catalog.

    Returns:
      (True,  "",                  [{tool, args}, ...])  on success
      (False, "human-readable err", [])                   on failure
    """
    calls = []
    for item in plan:
        ...
        calls.append({"tool": "myplugin_deploy", "args": {...}})
    return True, "", calls
```

Reference it from your workflow:

```python
Workflow(
    id="myplugin_provision",
    plan_validator="plugins.myplugin.mcp.translator.validate_plan",
    ...
)
```

On validation failure, the orchestrator feeds the error back as the
agent's next observation so it can correct and retry up to `max_iters`.

---

## 7. UI components (optional)

Vue components live in `plugins/<your_plugin>/gui/views/*.vue`. Magma's
`prebundle.js` copies them into the Caldera SPA at build time.

### 7.1 Workflow session page

A workflow's `ui_component: "my_workflow.vue"` resolves to
`plugins/<your_plugin>/gui/views/my_workflow.vue`. Built-in workflows
omit `ui_component` (or point at `author.vue` / `plan_execute.vue`),
which routes them through the shared chat module at
[gui/views/chat/ChatWorkflow.vue](gui/views/chat/ChatWorkflow.vue).

Most third-party workflows do not need a custom session page: the
shared chat component is workflow-agnostic and renders correctly off
the workflow registration alone (display_name, description,
accepted_capabilities, supports_chat_history, example_prompts). If
your workflow needs custom rendering, look at
[gui/views/chat/ChatWorkflow.vue](gui/views/chat/ChatWorkflow.vue) for
the orchestrator and re-use these pieces:

- [gui/views/chat/composables/useMcpRun.js](gui/views/chat/composables/useMcpRun.js) drives the
  POST /execute + GET /status poll loop and exposes reactive run state.
- [gui/views/chat/composables/useTrajectory.js](gui/views/chat/composables/useTrajectory.js) parses
  the DSPy ReAct trajectory into thoughts and (Author-specific) ability
  / adversary cards.
- [gui/views/format_result.js](gui/views/format_result.js)'s
  `formatProcessResult` helper safely renders bold + nested bullets.
- The leaf chat components (ChatTranscript, ChatMessage, ChatThoughts,
  ChatComposer, ChatLoadingState) compose into the standard chat shape.

### 7.2 Capability settings panel

A capability's `ui_settings_component: "my_attack_settings.vue"`
resolves to `plugins/<your_plugin>/gui/views/my_attack_settings.vue`.
The MCP shell renders it inside a collapsible "Capability Settings" box
on the workflow session page.

The component receives:

- a `globalConfig` object from `inject("mcpGlobalConfig")` — read/write
  user settings to `globalConfig.capabilitySettings[<your_id>]`;
  changes auto-persist to localStorage.

### 7.3 Magma rebuild

After you add or modify Vue files:

```
cd plugins/magma && npm run build
```

then reload the page.

---

## 8. Discovery model

The MCP plugin scans `plugins/*/` once at `enable()` and caches the
registries on `MCPService`. Concretely
([plugins/mcp/hook.py](hook.py)):

| Discovery scan | Looks for | Behavior on bad input |
|---|---|---|
| Servers ([app/discovery/servers.py](app/discovery/servers.py)) | `<plugin>/mcp_server.py` | `MCP_METADATA` parsed via AST; missing or non-literal → defaults |
| Workflows ([app/discovery/workflows.py](app/discovery/workflows.py)) | `<plugin>/mcp/workflows.py` exposing `WORKFLOWS = [...]` | Import errors logged, plugin skipped, rest of registry continues |
| Capabilities ([app/discovery/capabilities.py](app/discovery/capabilities.py)) | `<plugin>/mcp/capabilities.py` exposing `CAPABILITIES = [...]` | Same as workflows |

**Servers are AST-parsed**, not imported, so a syntactically broken
`mcp_server.py` won't crash the parent. Workflows and capabilities are
imported because they reference Python classes; an import failure in
one plugin won't take down others.

A plugin is rediscovered only on Caldera restart — there is no hot
reload.

---

## 9. Testing

### 9.1 Spawn smoke

The single most useful test verifies your server boots and lists tools.
Mirror
[plugins/mcp/tests/test_range_integration.py:test_range_server_spawns_and_lists_tools](tests/test_range_integration.py):

```python
import os
import asyncio
from pathlib import Path
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


VENV_PY = "/path/to/your/venv/bin/python"
SERVER  = Path(__file__).resolve().parents[1] / "mcp_server.py"


@pytest.mark.asyncio
async def test_my_server_spawns_and_lists_tools():
    env = os.environ.copy()
    env.setdefault("CALDERA_URL", "http://localhost:8888/api/v2/")
    env.setdefault("CORE_CALDERA_API_KEY", "ADMIN123")
    params = StdioServerParameters(command=VENV_PY, args=[str(SERVER)], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
    names = [t.name for t in tools]
    assert names, "server exposed zero tools"
    assert all(n.startswith("myplugin_") for n in names), \
        f"unprefixed tool names: {names}"
```

Listing tools doesn't require Caldera to be running, so this test is
fast and runs in CI.

### 9.2 Discovery smoke

Verify the framework actually finds your contributions:

```python
from pathlib import Path
from plugins.mcp.app.discovery.servers import discover_mcp_servers
from plugins.mcp.app.discovery.workflows import discover_workflows
from plugins.mcp.app.discovery.capabilities import discover_capabilities


def test_my_plugin_is_discovered():
    plugins_root = Path(__file__).resolve().parents[3]
    assert "myplugin" in discover_mcp_servers(plugins_root)
    # if you ship a workflow:
    assert any(w.id.startswith("myplugin_") for w in discover_workflows(plugins_root).values())
    # if you ship a capability:
    assert any(c.id.startswith("myplugin_") for c in discover_capabilities(plugins_root).values())
```

### 9.3 End-to-end

After unit smoke passes, do a manual round-trip:

1. Open the MCP plugin in Caldera.
2. Confirm your server appears in the per-workflow server checklist.
3. Tick it on, submit a prompt that should exercise one of your tools.
4. Watch the Thoughts panel; confirm the agent calls your tool by its
   prefixed name.
5. Watch the Result panel; confirm `process_result` reflects what your
   tool returned.

---

## 10. What not to do

- **Don't import from `plugins.mcp.app.mcp_svc` or `plugins.mcp.app.mcp_api`.**
  Those are framework internals. The stable surface is
  `plugins.mcp.app.workflows.base`,
  `plugins.mcp.app.capabilities.base`, and
  `plugins.mcp.app.config` /
  `plugins.mcp.app.dspy_env` for env-var constants.
- **Don't write to MLflow as a state store.** It's observability only.
  Return your data via the workflow's `run()` return value; the
  orchestrator caches it for the UI.
- **Don't expose tools that bypass the LLM** (e.g. tools that take
  free-form natural language and re-prompt internally). Tools should be
  deterministic API wrappers; reasoning is the agent's job.
- **Don't hard-code credentials.** Always read from environment
  variables the framework supplies (`CALDERA_URL`,
  `CORE_CALDERA_API_KEY`, `DSPY_*`). For your own external services,
  document the env var name in your plugin's README and read it the
  same way.
- **Don't share Python state between subprocess and parent.** Each
  `mcp_server.py` runs as its own process; module globals don't cross
  the boundary. State that must persist lives in Caldera's REST API or
  your plugin's own backing store.
- **Don't catch and swallow tool errors silently.** Return the error
  in the tool's response payload so the agent can react and the
  observability layer captures the failure:
  ```python
  if response.status_code != 200:
      return {"error": f"upstream returned {response.status_code}: {response.text}"}
  ```

---

## 11. Reference: a minimal working server

The smallest possible plugin contribution that does something useful:

```
plugins/hello/
├── hook.py
└── mcp_server.py
```

`mcp_server.py`:

```python
import os
from mcp.server.fastmcp import FastMCP


MCP_METADATA = {
    "display_name": "Hello",
    "default_enabled": False,
    "description": "Trivial echo and greeting tools",
}

mcp = FastMCP("Hello MCP Server")


@mcp.tool(name="hello_echo")
def hello_echo(text: str) -> str:
    """Return the input string unchanged. Useful as a sanity tool."""
    return text


@mcp.tool(name="hello_greet")
def hello_greet(name: str = "world") -> str:
    """Return 'Hello, <name>!'."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    mcp.run()
```

Restart Caldera. The MCP plugin's splash page will list `hello` under
discovered servers; any workflow with `optional_servers` including
`hello` will let the user toggle it on, and the agent will be able to
call `hello_echo` and `hello_greet` on demand.

---

## 12. Reference: the canonical extension

[plugins/range/mcp_server.py](../range/mcp_server.py) and the
`plugins/range/mcp/` directory are the reference implementation of this
contract end-to-end — server, tools, and (eventually) workflows /
translator. When the contract above is ambiguous, RANGE is the
ground truth.
