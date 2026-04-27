# MCP Plugin Refactor Plan

> Status: **proposal** — not yet executed.
> Owner: TBD.
> Reviewer: please leave inline notes / objections; sections tagged `[OPEN]` need a decision before step 1 starts.

---

## 1. Executive summary

Refactor the MCP plugin from a flat, hard-coded shape (`Ability Factory` and `Operation Planner` baked into both the backend and the Vue UI) into a **composable foundation** that other Caldera plugins extend.

The redesign rests on **three orthogonal building blocks** discovered at boot:

| Block | What it is | Owns |
|---|---|---|
| **MCP Server** | A subprocess exposing tools the LLM can call | RANGE owns `range_*`, MCP owns `caldera_core` |
| **Workflow** | An agent persona — signature + UI page + which servers it accepts | MCP ships two general workflows; plugins can ship their own |
| **Capability** | An orthogonal modifier that enriches the agent's prompt with extra context (RAG today, ATT&CK lookup tomorrow…) | MCP owns the foundation capabilities |

Plus, for the use cases that need structured infrastructure inference (CTI → environment provisioning), **two new architectural layers**:

| Layer | What it does | Lives in |
|---|---|---|
| **Inference Scaffolding** | Forces the LLM to emit structured plans, not free-form prose | MCP (signature shape + optional pre-processor capability) |
| **Spec-to-Call Translation** | Validates the LLM's plan against the plugin's catalog and emits parameterized tool calls | The plugin that owns the tools (e.g. RANGE) |

The end state: the MCP plugin is a marketplace. Adding a new workflow or capability to the platform requires **zero changes to MCP framework code** — it's a file drop in the contributing plugin.

---

## 2. Problems with the current design

| # | Problem | Where it shows up today |
|---|---|---|
| 1 | "Ability Factory" and "Operation Planner" are hard-coded tabs in `mcp.vue` | New workflows require forking the MCP plugin |
| 2 | `ExecuteStyle` enum encodes (workflow × capability) as a single string (`factory`, `rag_factory`, `planner`, `rag_planner`) | Combinatorial explosion when a third capability lands |
| 3 | Two near-duplicate signature classes per workflow (`DSPyCalderaFactoryClient` + `DSPyCalderaFactoryClientWithRAG`) | RAG injection logic is duplicated and entangled with workflow logic |
| 4 | RANGE MCP tools are reachable from the Ability Factory tab, even though the Factory signature explicitly forbids deploy actions | Soft-fence-only; user gets confusing tool offerings |
| 5 | Server-checklist is a global setting in Global Model Config, but only one workflow at a time consumes it | The "RANGE leaking into Factory" bug is a direct symptom |
| 6 | Tool docstrings in `range/mcp_tools/*` are the only thing helping the LLM bind CTI prose to deploy calls | No deterministic validation, no parameter defaulting, no introspection |
| 7 | Workflow client files mix HTTP / orchestration / signature / subprocess plumbing in one big module each | Hard to follow; hard to test in isolation |
| 8 | `factory.py` (subprocess DSPy bootstrap) and `mcp_factory_client.py` (Ability Factory workflow) share the word "factory" by accident | Naming collision, ongoing confusion |
| 9 | `app/` is a flat junk drawer | Opening the directory teaches you nothing about the architecture |

---

## 3. Architectural vision

### 3.1 The three composable blocks

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  MCP Servers    │  │   Workflows     │  │  Capabilities   │
│                 │  │                 │  │                 │
│  TOOLS the LLM  │  │  AGENT persona  │  │  MODIFIERS that │
│  can call       │  │  + tool scope   │  │  enrich the     │
│                 │  │  + UI page      │  │  agent's prompt │
│                 │  │                 │  │                 │
│  caldera_core,  │  │  Author,        │  │  RAG (CTI),     │
│  range, …       │  │  Plan & Execute │  │  ATT&CK lookup, │
│                 │  │                 │  │  …              │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                   ┌────────────────────┐
                   │  Discovery Layer   │
                   │  (boot-time scan)  │
                   └────────────────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │  HTTP API + UI     │
                   │  (data-driven)     │
                   └────────────────────┘
```

### 3.2 Composition rule

> **A run is `(workflow_id) × (enabled servers ⊆ workflow's allowed set) × (enabled capabilities ⊆ workflow's accepted set)`.**

Each axis is independent. Adding a new capability uplifts every workflow that accepts it without touching workflow code. Adding a new server adds verbs without touching anything else.

### 3.3 The two extra layers for serious infrastructure work

For workflows that need to translate prose context (CTI reports) into parameterized tool calls (e.g., `range_vm_deploy(...)` with the right image / CPU / RAM), the architecture adds:

```
RAG (capability)
   │ retrieves CTI chunks
   ▼
[Optional] CTI Spec Extractor (capability)
   │ separate LLM call → typed InfrastructureSpec
   ▼
Workflow signature with structured output
   │ LLM emits a typed DeploymentPlan, not prose
   ▼
Plan Validator + Translator  (lives in the tool-owning plugin)
   │ validates plan against plugin's catalog;
   │ fills defaults; emits parameterized tool calls
   ▼
MCP server tool calls execute (range_vm_deploy etc.)
```

Naked `LLM + tools` works for `"list my profiles"`. The two-layer pattern is needed for `"build infrastructure that mirrors APT29"`.

### 3.4 The "Plan-then-Execute" workflow phase model

A workflow can declare it is a **two-phase** workflow:

1. **Plan phase** — agent produces a structured plan (DSPy signature with typed `OutputField`).
2. **Validate phase** — deterministic Python in the tool-owning plugin checks the plan against reality.
3. **Execute phase** — translator turns the validated plan into the actual sequence of tool calls.

If validation fails, the validator's error message becomes the next observation; the agent retries. This is the missing piece between LLM inference and reliable infrastructure provisioning.

---

## 4. Final directory structure

### 4.1 MCP plugin (the foundation)

The MCP plugin's `app/` directory has two halves:

- **Framework half** (top of `app/` + the four foundation subfolders) — the contract
  every other plugin extends. Stable. Touched rarely.
- **caldera_core extension half** (`mcp_server.py` + `mcp_tools/`) — what the MCP
  plugin contributes as a peer to RANGE. Stays flat **deliberately** — see §4.3
  for why the MCP plugin doesn't mirror RANGE's `mcp/` folder pattern.

```
plugins/mcp/
├── hook.py                             # plugin entry — calls into framework
├── conf/default.yml                    # llm config + api_base + ${API_KEY}
├── data/                               # uploaded RAG bundles
├── static/, templates/, gui/           # GUI assets — re-organized below
├── tests/
│   └── test_range_integration.py
│
├── REFACTOR_PLAN.md                    # this document
│
├── app/
│   │  ────── FRAMEWORK ──────
│   ├── mcp_api.py                      # HTTP routes (Caldera convention: top-level)
│   ├── mcp_svc.py                      # orchestration / business logic
│   ├── mcp_gui.py                      # splash route
│   ├── dspy_env.py                     # subprocess DSPy LM bootstrap (was factory.py)
│   │
│   ├── discovery/                      # finds extensions at boot
│   │   ├── __init__.py
│   │   ├── servers.py                  # was server_registry.py
│   │   ├── workflows.py                # NEW
│   │   └── capabilities.py             # NEW
│   │
│   ├── workflows/                      # foundation workflows (reusable by any plugin)
│   │   ├── __init__.py
│   │   ├── base.py                     # Workflow dataclass + run-context types
│   │   ├── author.py                   # was mcp_factory_client.py
│   │   └── plan_execute.py             # was mcp_planner_client.py
│   │
│   ├── capabilities/                   # foundation capabilities (reusable by any workflow)
│   │   ├── __init__.py
│   │   ├── base.py                     # Capability dataclass
│   │   ├── rag.py                      # was rag.py
│   │   └── cti_spec_extractor.py       # NEW (optional second-pass capability)
│   │
│   │  ────── caldera_core EXTENSION (the MCP plugin's own MCP server) ──────
│   ├── mcp_server.py                   # caldera_core entrypoint (Caldera contract)
│   └── mcp_tools/                      # caldera_core's tool modules
│       ├── __init__.py
│       ├── abilities.py                # core_get_abilities*, core_create_ability
│       ├── adversaries.py              # core_get_adversary*, core_create_adversary
│       ├── agents.py
│       ├── operations.py
│       └── health.py
│
└── gui/views/
    ├── mcp.vue                         # shell — renders discovered workflows
    ├── author.vue                      # was local_mcp_ability_factory.vue
    ├── plan_execute.vue                # was public_mcp_ability_factory.vue
    ├── mcp_history.vue
    └── components/
        ├── WorkflowCard.vue            # NEW — single workflow card on home page
        ├── ServerChecklist.vue         # NEW — reusable per-workflow server toggles
        ├── CapabilityPanel.vue         # NEW — wraps a capability's settings UI
        └── RAGSettings.vue             # NEW — RAG capability settings (file picker, topk, embed model)
```

### 4.2 RANGE plugin (the canonical extension)

External plugins follow the **`mcp/` folder pattern** — `mcp_server.py` at plugin
root (the Caldera contract entrypoint), everything else MCP-related grouped
inside an `mcp/` subfolder.

```
plugins/range/
├── (RANGE's own existing files: range_cloud_gui.py, range_onprem_gui.py, etc.)
│
├── mcp_server.py                       # ✅ Caldera contract entrypoint — stays at root
│                                          (this is what discovery scans for)
│
└── mcp/                                # everything else MCP-related grouped here
    ├── __init__.py
    ├── tools/                          # @mcp.tool() implementations (was mcp_tools/)
    │   ├── __init__.py
    │   ├── profiles.py
    │   ├── templates.py
    │   ├── images.py
    │   ├── vms.py
    │   ├── inventory.py
    │   ├── features.py
    │   ├── introspection.py            # NEW — range_template_describe, etc.
    │   └── plan_executor.py            # NEW — exposes range_execute_plan tool
    ├── workflows.py                    # NEW — WORKFLOWS = [Workflow(...)] (optional)
    ├── capabilities.py                 # NEW — CAPABILITIES = [Capability(...)] (optional, future)
    └── translator.py                   # NEW — validate_plan() called by workflow plan_validator
```

### 4.3 The naming rule (and the one intentional asymmetry)

> 1. Top-level `app/*.py` files use the `mcp_` prefix (matches Caldera plugin convention).
> 2. Files inside subfolders drop the prefix (the path namespaces them).
> 3. A folder needs ≥3 things to exist. One-file folders live flat.
> 4. **External plugins** group their MCP contributions under `mcp/`.
>    **The MCP plugin itself** does NOT — see below.

#### Why the MCP plugin keeps `mcp_server.py + mcp_tools/` flat instead of using `mcp/`

A consistency-first reading would put the caldera_core extension in
`plugins/mcp/app/mcp/`. We **explicitly do not** because:

| Cost | Why it bites |
|---|---|
| **Path doubling** | `from plugins.mcp.app.mcp.tools.abilities import …` — three "mcp/app/mcp" segments back to back. Hard to read, hard to type, hard to autocomplete. RANGE doesn't have this problem (`plugins.range.mcp.tools` reads cleanly) because the plugin's name doesn't collide with the folder name. |
| **Server divorced from its tools** | For RANGE, `mcp_server.py` (root) sits adjacent to `mcp/tools/` (its tools). For MCP, `app/mcp_server.py` would import "down into" `app/mcp/tools/` across a folder boundary — server and tools no longer adjacent. |
| **Two patterns within one plugin** | Framework code uses flat-with-subfolders; the extension would mirror an external plugin shape. Contributors have to learn both. |
| **Discovery special-case** | Foundation workflows live at `app/workflows/`; if extension stuff lived at `app/mcp/`, discovery would need a one-off rule for the MCP plugin. |

The structural insight ("group MCP-related code under a folder") still wins for
every plugin **except** the one literally named `mcp`. Asymmetry is the right
trade — documented here so it's a deliberate decision, not an oversight.

---

## 5. Plugin contracts

What an external plugin drops to extend MCP:

| Path | Purpose | Required? | Discovered by |
|---|---|---|---|
| `plugins/<name>/mcp_server.py` | Defines the plugin's MCP server entry. Must contain `MCP_METADATA = {...}` literal at the top (parsed by AST without executing). Stays at plugin root — it's the Caldera-convention entrypoint discovery scans for. | If you bring tools | `discovery/servers.py` |
| `plugins/<name>/mcp/workflows.py` | Defines `WORKFLOWS = [Workflow(...), ...]` — workflow registrations. | Optional | `discovery/workflows.py` |
| `plugins/<name>/mcp/capabilities.py` | Defines `CAPABILITIES = [Capability(...), ...]` — capability registrations. | Optional | `discovery/capabilities.py` |
| `plugins/<name>/mcp/translator.py` | Exposes a `validate_plan(...)` function for plan-then-execute workflows. Referenced by `Workflow.plan_validator` dotted path. | Optional | Loaded on demand by orchestrator |
| `plugins/<name>/mcp/tools/` | The plugin's `@mcp.tool()` implementations imported by `mcp_server.py`. | If you bring tools | imported from `mcp_server.py` |

A plugin can ship any subset. Discovery walks `plugins/*/` once at `enable()` time, collects whatever it finds, and merges with the framework's built-in registrations.

**Why the asymmetry between `mcp_server.py` (root) and `mcp/...` (folder):** discovery scans for `mcp_server.py` at the plugin root because that's the long-standing Caldera plugin convention — changing it would force every existing MCP-using plugin to relocate its entrypoint. Everything *else* is new contract surface, so we group it under `mcp/` from the start.

---

## 6. Core abstractions

### 6.1 `Workflow` dataclass

```python
# plugins/mcp/app/workflows/base.py
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any
import dspy

@dataclass
class Workflow:
    id: str                              # "author", "plan_execute", "range_provision"
    display_name: str                    # "Author", "Plan & Execute"
    description: str

    # The agent persona — DSPy signature class
    signature: type[dspy.Signature]

    # Server scope
    required_servers: list[str]          # must be present; pinned-on in UI
    optional_servers: list[str]          # user can toggle in UI

    # Capability scope
    accepted_capabilities: list[str]     # capability ids the workflow can consume

    # Two-phase pattern (optional)
    plan_validator: str | None = None    # dotted path to validator function;
                                         # if set, the workflow runs in plan-then-execute mode

    # UI integration
    ui_component: str = ""               # vue component path; "" → use generic shell
    example_prompts: list[str] = field(default_factory=list)

    # Execution entry point
    run: Callable[..., Awaitable[dict[str, Any]]] = None
```

### 6.2 `Capability` dataclass

```python
# plugins/mcp/app/capabilities/base.py
from dataclasses import dataclass
from typing import Callable, Awaitable, Any

@dataclass
class Capability:
    id: str                              # "rag", "cti_spec", "attack_lookup"
    display_name: str
    description: str

    # Async function that runs before the workflow's main agent loop.
    # Receives (prompt, settings) and returns a dict merged into the
    # workflow signature's input fields.
    enrich: Callable[[str, dict], Awaitable[dict[str, Any]]]

    # Optional UI for the capability's settings (file picker, topk slider, etc.)
    ui_settings_component: str = ""

    # Field names this capability contributes; helps the UI show users
    # which workflows can consume which capabilities.
    contributes_fields: list[str] = None
```

### 6.3 Example workflow definition

```python
# plugins/mcp/app/workflows/plan_execute.py
from plugins.mcp.app.workflows.base import Workflow

class PlanExecuteSignature(dspy.Signature):
    """Plan and execute operations / infrastructure provisioning.

    You may receive optional CTI context describing target environments
    or threat actor TTPs. When present, plan to produce a deployable
    environment that matches it. When absent, follow the user's intent
    using available tools.
    """
    user_intent: str = dspy.InputField()
    cti_context: str = dspy.InputField(desc="Optional CTI context", default="")
    available_catalog: str = dspy.InputField(
        desc="JSON catalog of available infrastructure primitives", default=""
    )

    plan: list[dict] = dspy.OutputField(desc="Structured deployment plan")
    rationale: str = dspy.OutputField(desc="Why this plan matches the request")

WORKFLOWS = [
    Workflow(
        id="plan_execute",
        display_name="Plan & Execute",
        description="Plan operations or infrastructure provisioning, optionally grounded in CTI.",
        signature=PlanExecuteSignature,
        required_servers=["caldera_core"],
        optional_servers=["range"],
        accepted_capabilities=["rag", "cti_spec"],
        plan_validator="plugins.range.mcp.translator.validate_plan",
        ui_component="plan_execute.vue",
        example_prompts=[
            "Plan an emulation against the Discovery adversary",
            "Build infrastructure that resembles APT29's typical target environment",
            "Stand up a small ICS testbed with 2 Windows hosts and 1 Linux jumpbox",
        ],
        run=run,  # async function in same file
    ),
]
```

### 6.4 Example capability definition

```python
# plugins/mcp/app/capabilities/rag.py
from plugins.mcp.app.capabilities.base import Capability

async def enrich(prompt: str, settings: dict) -> dict:
    """Returns {"cti_context": "..."} given selected RAG files."""
    rag_files = settings.get("rag_files") or []
    if not rag_files:
        return {}
    rag = build_rag_service(rag_files, settings)
    ctx = rag.get_context_for_task(prompt)
    return {"cti_context": format_rag_context(ctx)}

CAPABILITIES = [
    Capability(
        id="rag",
        display_name="CTI Ingestion (RAG)",
        description="Embed uploaded CTI bundles and inject relevant chunks as context.",
        enrich=enrich,
        ui_settings_component="rag_settings.vue",
        contributes_fields=["cti_context"],
    ),
]
```

### 6.5 Plan validator example (RANGE-side)

```python
# plugins/range/mcp/translator.py
from typing import TypedDict

class PlannedHost(TypedDict):
    role: str               # "domain_controller", "endpoint", "jumpbox"
    os_family: str          # "windows", "linux"
    cpu: int | None
    memory_gb: int | None
    network: str | None

# Catalog: maps abstract roles to concrete RANGE templates + defaults
_ROLE_CATALOG = {
    "domain_controller": {
        "template": "ad_dc",
        "image": "ws2019_eval",
        "defaults": {"cpu": 4, "memory_gb": 8},
    },
    "endpoint": {
        "template": "win10_workstation",
        "image": "win10_22h2",
        "defaults": {"cpu": 2, "memory_gb": 4},
    },
    "jumpbox": {
        "template": "ubuntu_jumpbox",
        "image": "ubuntu_2204",
        "defaults": {"cpu": 1, "memory_gb": 2},
    },
}

def validate_plan(plan: list[PlannedHost]) -> tuple[bool, str, list[dict]]:
    """Validates a plan against the catalog. Returns (ok, error_msg, calls).

    On success: returns (True, "", [tool_call, ...]) — concrete deploy calls
    with all params filled in.

    On failure: returns (False, "human-readable error", []). The error is
    surfaced back to the LLM as the next observation so it can correct.
    """
    calls = []
    for host in plan:
        role = host["role"]
        if role not in _ROLE_CATALOG:
            return False, f"Unknown role '{role}'. Available: {list(_ROLE_CATALOG)}", []
        spec = _ROLE_CATALOG[role]
        defaults = spec["defaults"]
        calls.append({
            "tool": "range_vm_deploy",
            "args": {
                "template": spec["template"],
                "image": spec["image"],
                "cpu": host.get("cpu") or defaults["cpu"],
                "memory_gb": host.get("memory_gb") or defaults["memory_gb"],
                "network": host.get("network") or "lab_net_1",
            },
        })
    return True, "", calls
```

---

## 7. Backend orchestration

### 7.1 New `_run_execution` flow (replaces today's `ExecuteStyle` switch)

```
1. Look up workflow by `workflow_id` from the registry.
2. Filter `enabled_servers` against workflow's `required ∪ optional`.
3. Run each enabled capability's `enrich(prompt, settings)`. Merge results into a `context` dict.
4. Spawn the required + opted-in MCP servers as subprocesses. Build the merged tool list.
5. If workflow has `plan_validator`:
       a. Run the agent; collect the structured `plan` output.
       b. Resolve the validator function and call it.
       c. If invalid: feed the error back as the next thought, retry up to N times.
       d. If valid: execute the validator's returned tool-call sequence.
   Else:
       a. Run the agent's standard ReAct loop until `finish` or `max_iters`.
6. Log trajectory tags as today; return `{run_id, process_result}`.
```

### 7.2 New HTTP routes

| Method | Route | Returns |
|---|---|---|
| `GET` | `/plugin/mcp/workflows` | discovered workflow registry (id, display, description, accepted_capabilities, required+optional servers, example_prompts, ui_component) |
| `GET` | `/plugin/mcp/capabilities` | discovered capability registry |
| `GET` | `/plugin/mcp/servers` | discovered server registry (existing, unchanged) |
| `GET` | `/plugin/mcp/defaults` | yaml-resolved LM defaults (existing, unchanged) |
| `POST` | `/plugin/mcp/execute` | now takes `{workflow_id, prompt, enabled_servers, enabled_capabilities, capability_settings, lm_config}` |

### 7.3 `ExecuteStyle` enum — deletion

Removed entirely after step 6. The `factory` / `planner` / `rag_factory` / `rag_planner` strings dissolve into `(workflow_id, enabled_capabilities)`.

---

## 8. Frontend changes (`mcp.vue` and below)

### 8.1 `mcp.vue` shell becomes data-driven

| Today | After |
|---|---|
| Three hard-coded cards: Factory / Planner / History | One card per discovered workflow + History card |
| Server checklist in Global Model Config | Removed — moved into each workflow's session page (scoped to that workflow's `required ∪ optional`) |
| `RAG TopK` and `RAG Embed Model` in Global Model Config | Removed — moved into the RAG capability's `RAGSettings.vue` panel; Global Model Config retains LM credentials/limits only |
| Hard-coded `selectedPath` enum | Driven by workflow `id` from `/plugin/mcp/workflows` |
| Each session page knows its own type string | Each session page declares its `workflow_id` once and posts it |
| `globalConfig` localStorage shape | Adds `capability_settings: {<capability_id>: {...}}` — capability settings persist **globally** (a user's RAG preference applies to every workflow that accepts RAG, not per-workflow) |

### 8.2 Each workflow's session page

| Section | Source |
|---|---|
| Title + description | workflow registration |
| Example prompts | workflow registration `example_prompts` |
| Server checkboxes | filtered to `workflow.required ∪ workflow.optional`; required pinned-on |
| Capability panels | one per `accepted_capabilities`; each renders its `ui_settings_component` |
| Trajectory rendering | shared component; can be augmented per-tool via plugin-supplied renderer hooks (future) |

### 8.3 New Vue components

| File | Purpose |
|---|---|
| `gui/views/components/WorkflowCard.vue` | Single workflow card on the home page |
| `gui/views/components/ServerChecklist.vue` | Reusable checkbox list (was inline in mcp.vue) |
| `gui/views/components/CapabilityPanel.vue` | Wraps a capability's settings |
| `gui/views/components/RAGSettings.vue` | RAG capability's settings (file picker, embed model, topk) |

### 8.4 What plugins ship UI-side

External plugins can ship their own session-page Vue components inside their plugin's `gui/views/` directory. The `prebundle.js` script in `magma/` already copies plugin GUI files; it just needs to honor a per-workflow path convention (e.g., the workflow registration's `ui_component` field is interpreted relative to the plugin's `gui/views/`). [OPEN — see §13.1]

---

## 9. Where each piece lives (the dividing line)

| Concern | Plugin | Path | Notes |
|---|---|---|---|
| Discovery + framework contracts | **MCP** | `app/discovery/`, `app/workflows/base.py`, `app/capabilities/base.py` | Stable foundation |
| Two general workflows (Author, Plan & Execute) | **MCP** | `app/workflows/{author,plan_execute}.py` | Cover most use cases |
| RAG capability (mechanism) | **MCP** | `app/capabilities/rag.py` | Generic info-retrieval primitive |
| CTI Spec Extractor capability | **MCP** | `app/capabilities/cti_spec_extractor.py` | Generic NLU on prose CTI |
| `caldera_core` MCP server + tools | **MCP** | `app/mcp_server.py` + `app/mcp_tools/` (flat — see §4.3) | Caldera's own API surface |
| HTTP API + UI shell + reusable Vue components | **MCP** | `app/mcp_api.py`, `gui/views/` | Foundation surface |
| `range_*` MCP server | **RANGE** | `mcp_server.py` (root) | Caldera contract |
| `range_*` tool implementations | **RANGE** | `mcp/tools/*.py` | Inside the `mcp/` folder per §4.2 |
| `range_template_describe` and other introspection tools | **RANGE** | `mcp/tools/introspection.py` | RANGE knows its own catalog |
| RANGE's plan validator + translator | **RANGE** | `mcp/translator.py` | Deterministic spec-to-call binding |
| RANGE-specific UI (e.g., "VM provisioned" badges) | **RANGE** | `gui/views/*.vue` | Domain-specific UX |
| RANGE-specific workflows (if any beyond Plan & Execute) | **RANGE** | Optional |

### The single test for "where does it go?"

> **If a hypothetical future plugin would want to reuse it → MCP. If only this plugin will ever want it → the plugin.**

---

## 10. Migration plan — step by step

Each step is one commit. Steps 1–6 are pure refactor with no user-visible change. Step 7 is the first user-visible win. Steps 8–9 unlock the green-field work.

### Step 1 — Mechanical move

Pure `git mv` + import-fix sweep. No logic changes.

**MCP plugin (framework half stays flat — the `mcp/` pattern doesn't apply here, see §4.3):**
- `app/mcp_factory_client.py` → `app/workflows/author.py`
- `app/mcp_planner_client.py` → `app/workflows/plan_execute.py`
- `app/server_registry.py` → `app/discovery/servers.py`
- `app/rag.py` → `app/capabilities/rag.py`
- `app/factory.py` → `app/dspy_env.py`
- `app/mcp_server.py` and `app/mcp_tools/` — **unchanged**. Caldera_core extension stays flat; the in-place `mcp_tools/` split (one tool module per domain) is a deferred follow-on commit.

**RANGE plugin (adopts the `mcp/` folder pattern):**
- `plugins/range/mcp_tools/` → `plugins/range/mcp/tools/` (rename only; contents unchanged)
- `plugins/range/mcp_server.py` — **unchanged** (Caldera contract entrypoint stays at root)
- Imports inside RANGE's `mcp_server.py` updated: `from mcp_tools import ...` → `from mcp.tools import ...`

**Magma bundling note:**
All Vue edits in this and following steps happen in `plugins/mcp/gui/views/`.
The `plugins/magma/prebundle.js` script copies plugin GUI files into
`magma/src/plugins/<name>/views/` at build time. If `prebundle.js` has any
hard-coded filename allowlist, update it to honor the renames
(`local_mcp_ability_factory.vue` → `author.vue`, etc.).

**Verify:** existing tests still pass; existing routes still respond identically; the magma build (`npm run build`) succeeds.

### Step 2 — Define `Workflow` and `Capability` dataclasses

Add `app/workflows/base.py` and `app/capabilities/base.py`. Empty registries; nothing consumes them yet. Pure type definitions.

### Step 3 — Wrap existing factory + planner as `Workflow` instances

Inside `app/workflows/author.py` and `app/workflows/plan_execute.py`, declare a module-level `WORKFLOWS = [Workflow(...)]`. The orchestrator still routes by old `ExecuteStyle` strings — workflows aren't consumed yet. No behavior change.

### Step 4 — Wrap RAG as a `Capability`

Inside `app/capabilities/rag.py`, declare `CAPABILITIES = [Capability(id="rag", enrich=..., ...)]`. Orchestrator still uses old `_build_rag_service_from_files` path. No behavior change.

### Step 5 — Discovery for workflows + capabilities

Add `app/discovery/workflows.py` and `app/discovery/capabilities.py`, mirroring how `servers.py` works. They walk `plugins/*/mcp_workflows.py` and `plugins/*/mcp_capabilities.py`. Internal-only — nothing exposes them yet. `hook.py` calls them at `enable()` and stores the merged registries on `MCPService`.

### Step 6 — Switch the orchestrator + add API routes

The user-visible step.

- Replace `ExecuteStyle`-based dispatch in `mcp_svc._run_execution` with workflow-registry lookup.
- Add `GET /plugin/mcp/workflows` and `GET /plugin/mcp/capabilities` routes.
- `POST /plugin/mcp/execute` payload schema changes from `{type, config, enabled_servers}` → `{workflow_id, lm_config, enabled_servers, enabled_capabilities, capability_settings}`.
- Update `mcp.vue` to fetch `/workflows` and render cards dynamically. Remove the global server checklist and the RAG-specific fields (`RAG TopK`, `RAG Embed Model`) from Global Model Config — they move into per-workflow session pages and the RAG capability's `RAGSettings.vue` panel respectively.
- Update `author.vue` and `plan_execute.vue` to render scoped server checklists + capability panels.
- **Update the in-page "Extend & Customize" guide tab.** Today its `<pre v-pre>` snippet teaches users to add `LLMcustom = "custom"` to the `ExecuteStyle` enum — that enum no longer exists. Replace the example with a worked walkthrough of dropping `mcp/workflows.py` (and optionally `mcp/capabilities.py`, `mcp/translator.py`) in a plugin to contribute a new workflow.

After this: behavior is unchanged for the Author and Plan & Execute workflows. Server checklist is now per-workflow (RANGE no longer leaks into Author).

### Step 7 — Add the two-phase pattern

- Add `plan_validator` plumbing in `_run_execution`: when set on a workflow, the agent's structured `plan` output is fed to the validator; on failure, the error becomes the next observation; on success, the returned tool-call sequence is executed.
- Update `PlanExecuteSignature` to use typed structured output for `plan`.

### Step 8 — RANGE plugin contributes the translator + introspection tools

- New file `plugins/range/mcp/translator.py` with `validate_plan(...)`.
- New tool modules `plugins/range/mcp/tools/introspection.py` (`range_template_describe` etc.) and `plugins/range/mcp/tools/plan_executor.py` (`range_execute_plan`).
- (Optional) `plugins/range/mcp/workflows.py` declaring a RANGE-specific workflow if Plan & Execute proves insufficient.

After this: CTI → infra works end-to-end. User uploads a CTI bundle on the Plan & Execute page, ticks RAG, types intent. Agent emits a structured plan; validator gates it; concrete deploy calls execute.

### Step 9 — CTI Spec Extractor capability (optional polish)

Add `app/capabilities/cti_spec_extractor.py` with `enrich` doing a separate, structured LLM call to pre-process CTI text into an `InfrastructureSpec`. Enables workflows to receive both raw CTI chunks AND a typed pre-parsed spec.

---

## 11. Backwards compatibility

- **Steps 1–5** preserve all existing HTTP contracts and behavior. Existing UI continues to work.
- **Step 6** changes the `/execute` payload shape. UI is updated in the same commit. Anyone hitting `/execute` programmatically will need to switch from `{type: "factory"}` to `{workflow_id: "author"}`.
- **Step 6** removes the `ExecuteStyle` enum. There is no deprecation warning — this is a clean break.
- The `mcp_server.py` plugin contract (with `MCP_METADATA`) is **unchanged**. Existing plugin-provided MCP servers (RANGE) continue to work without modification.

---

## 12. Testing strategy

| Layer | Test | Where |
|---|---|---|
| Discovery | `test_discovery_finds_range_server` (already exists) | `tests/test_range_integration.py` |
| Discovery | `test_discovery_finds_workflows`, `test_discovery_finds_capabilities` (new) | `tests/test_discovery.py` |
| Workflow registry | Each built-in workflow round-trips through the registry | `tests/test_workflows.py` |
| Capability registry | Each built-in capability round-trips and `enrich` returns the documented field set | `tests/test_capabilities.py` |
| Spawn | `test_range_server_spawns_and_lists_tools` (already exists) | `tests/test_range_integration.py` |
| Orchestration | `test_factory_client_merges_core_and_range_tools` (already exists; rename) | `tests/test_range_integration.py` |
| Translator | `test_validate_plan_rejects_unknown_role`, `test_validate_plan_fills_defaults`, `test_validate_plan_emits_correct_calls` (new) | `plugins/range/tests/test_translator.py` |
| End-to-end | Smoke test: POST `/execute` with a Plan & Execute prompt + RAG bundle → MLflow run shows structured plan + range tool calls | manual or scripted, against running Caldera |

---

## 13. Open questions — decide before step 1

### 13.1 Plugin-contributed Vue components

How do plugin-shipped session pages get bundled by magma? Today `prebundle.js` copies all `plugins/*/gui/views/` into `magma/src/plugins/<name>/views/`. Workflow `ui_component` fields can reference these by path. **Need:** a clear convention. Proposal: `ui_component` is a path relative to the contributing plugin's `gui/views/` directory; the framework prepends the right magma path at render time.

### 13.2 Workflow + capability discovery filename — flat or directory?

Today: `plugins/<name>/mcp_workflows.py` (single file). If a plugin has multiple workflows, they all live in one file's `WORKFLOWS = [...]` list. Alternative: `plugins/<name>/mcp_workflows/__init__.py` directory. **Proposal:** start flat; upgrade to directory if a plugin actually has >3 workflows.

### 13.3 Required servers — hard-fail or graceful degrade?

If a workflow declares `required_servers=["range"]` and the RANGE plugin isn't installed, what happens?
- **(a)** Workflow doesn't appear in `/workflows` at all. Cleanest UX.
- **(b)** Workflow appears but is greyed out with "RANGE plugin required" tooltip. Slightly more discoverable; teaches users about installable plugins.

**Proposal:** (a) for v1, (b) when there are enough plugins to merit the affordance.

### 13.4 Capability enrichment — sequential or parallel?

If a workflow accepts multiple capabilities, do they `enrich()` sequentially or in parallel?
- Parallel is faster but risks overlapping field writes.
- Sequential is deterministic and easier to debug.

**Proposal:** sequential, in the order the user enabled them. Cap each at a sensible timeout (e.g., 30s) so a slow capability can't hang the whole run.

### 13.5 Plan validator — sync or async?

Validators may want to query other services (e.g., RANGE's own state for "does this network exist?"). **Proposal:** validator signature is `async def validate(plan, services) -> (ok, error, calls)`. Receives the Caldera services dict. Sync validators wrap themselves in `asyncio.iscoroutinefunction` check.

### 13.6 Capability ↔ workflow contract — by field name?

A capability declares `contributes_fields=["cti_context"]`. A workflow signature has an input field named `cti_context`. The framework merges them by **field name match**. If the names drift, the capability's output silently doesn't reach the agent.

- **Proposal:** the framework warns at registration time when a workflow declares `accepted_capabilities=[...]` but its signature has no input field matching any capability's `contributes_fields`. Catches drift early.

---

## 14. Out of scope (for now)

- Hot reload of discovered plugins (still requires Caldera restart).
- Schema validation of plugin contributions beyond "Workflow / Capability dataclass shape." Bad signatures or bad MCP servers fail at runtime, not registration.
- Authentication / authorization scoping per-workflow. Inherits Caldera's existing plugin auth model.
- Versioning / compatibility checks between plugins (e.g., RANGE workflow requires MCP plugin ≥ vX). YAGNI for v1.
- A general "renderer hook" framework for trajectory observations (e.g., RANGE registering a rendering function for `range_*` tool outputs). Future work — see §8.2.

---

## 15. What success looks like after step 9

1. **A user opens the MCP page and sees workflow cards driven entirely by discovery.** Removing a plugin removes its workflows from the UI without code changes.
2. **A user uploads a CTI report on the Plan & Execute tab, ticks the RAG capability, types "build infrastructure matching this report."** The agent retrieves CTI chunks, emits a structured deployment plan, the RANGE translator validates and binds parameters, range_vm_deploy calls execute. The whole chain is visible in MLflow.
3. **The MCP plugin code has zero references to `range_*` tools, the RANGE plugin, or any specific workflow beyond Author and Plan & Execute.** The dependency arrow points one way: extensions → foundation, never the reverse.
4. **A new contributor wants to add a "Threat Hunter" workflow.** They drop one file (`plugins/threathunter/mcp_workflows.py`) at their plugin root, restart Caldera, and a new card appears in the MCP page. They never touched the MCP plugin.
5. **The CTI → infrastructure path is reproducible and debuggable.** Each layer (RAG retrieval, structured plan, validator output, executed calls) is independently inspectable in MLflow trajectory tags.

---

## 16. Decision summary

| Question | Decision |
|---|---|
| Three composable blocks (servers, workflows, capabilities)? | **Yes** |
| Discovery-driven UI? | **Yes** |
| Two-phase plan-then-execute pattern? | **Yes**, opt-in per workflow via `plan_validator` |
| Spec-to-call translator lives in tool-owning plugin? | **Yes** (RANGE owns its translator) |
| RAG mechanism in MCP foundation? | **Yes** |
| RANGE workflow shipped by RANGE plugin? | **Optional** — Plan & Execute likely covers it |
| `ExecuteStyle` enum deleted? | **Yes**, in step 6 |
| Server checklist global vs per-workflow? | **Per-workflow**, scoped to required ∪ optional |
| Big-bang or iterative migration? | **Iterative**, 9 steps, each independently revertable |
| Top-level `app/` files keep `mcp_` prefix? | **Yes** |
| Subfolders drop `mcp_` prefix? | **Yes** |
| `core/`, `bridge/`, `servers/` folders for one-file concerns? | **No** — flatten |
| External plugins group MCP code under `mcp/` folder? | **Yes** (`mcp_server.py` at root, everything else inside `mcp/`) |
| MCP plugin itself uses the `mcp/` folder pattern? | **No** — keeps `app/mcp_server.py` + `app/mcp_tools/` flat to avoid `plugins.mcp.app.mcp.tools` path doubling. The asymmetry is documented in §4.3 |
| Global Model Config retains RAG TopK / Embed Model fields? | **No** — they move into `RAGSettings.vue` under the RAG capability |
| Capability settings persist per-workflow or globally? | **Globally** — one user preference per capability across all workflows that accept it |
