# MCP NLP UI Refactor — Chat-Style Workflow Page

**Status:** Implementation already on disk on branch `multi-mcp-layer`
(see "Reverting" below). This document describes the design so it can be
reviewed before being kept or rolled back.

**Scope:** the `author` workflow page only. The `plan_execute` workflow
(`public_mcp_ability_factory.vue`) is intentionally untouched in this pass.
No backend or MLflow changes — the chat UI shape is the structural
foundation for true multi-turn, but each prompt is still a single-shot
`/plugin/mcp/execute` call today.

---

## Goals

1. **Chat-style interface** — Claude.ai shape: scrolling transcript of
   messages, composer pinned to the bottom, multiple prompts per session.
2. **Expandable thoughts/reasoning** — collapsed by default per assistant
   response; one click reveals the trajectory and final reasoning.
3. **Clear loading feedback** during NLP processing — pulsing dots,
   animated "Thinking…" label, current backend stage shown.
4. **Full-screen layout** — replace the 75%-width box with a sidebar +
   main pane that fills the viewport.
5. **Big composer** — auto-grow textarea, 96–280px tall, multi-line
   prompts feel comfortable.
6. **Modular code** — break the 922-line `local_mcp_ability_factory.vue`
   into single-purpose components and composables.

---

## Module structure

```
plugins/mcp/gui/views/chat/
├── ChatWorkflow.vue           orchestrator (replaces single-page view)
├── ChatSidebar.vue            workflow config: servers, capabilities, RAG
├── ChatTranscript.vue         scrolling message list + empty state
├── ChatMessage.vue            user / assistant message bubble
├── ChatThoughts.vue           collapsible thoughts + reasoning panel
├── ChatComposer.vue           auto-grow input + send button
├── ChatLoadingState.vue       animated dots + stage indicator
└── composables/
    ├── useMcpRun.js           POST /execute + GET /status polling
    └── useTrajectory.js       derives thoughts, adversary, ability names
```

| File | Responsibility | Inputs | Outputs |
|------|---------------|--------|---------|
| `ChatWorkflow.vue` | Owns the message list and a single in-flight run | `workflow`, `capabilities` props; injected `$api`, `mcpGlobalConfig`, `mcpAvailableServers` | Renders sidebar + transcript + composer; emits `back` |
| `ChatSidebar.vue` | Workflow-scoped server/capability toggles + RAG picker | `workflow`, `capabilities`, `availableServers`, `globalConfig`, `$api`, `selectedRag`, `collapsed` | `update:selectedRag`, `back`, `toggle` |
| `ChatTranscript.vue` | Scrollable list, auto-scroll on new messages, near-bottom heuristic for live updates | `messages`, helpers | (none) |
| `ChatMessage.vue` | One bubble; switches on `role` + `status` | `message`, helpers | (none) |
| `ChatThoughts.vue` | Collapsible panel; closed by default | `thoughts`, `reasoning`, `adversary`, `abilityNames`, helpers | (none) |
| `ChatComposer.vue` | Textarea + send; Ctrl+Enter to submit, Enter for newline | `modelValue`, `disabled`, `examplePrompts` | `update:modelValue`, `submit` |
| `ChatLoadingState.vue` | Pulsing dots + stage queue with 6s dwell | `stage`, `label` | (none) |
| `useMcpRun.js` | One run lifecycle: POST `/execute`, then poll `/status` until terminal | `$api` | reactive `status`, `stage`, `runId`, `prompt`, `reasoning`, `finalResult`, `trajectory`, `errorMessage`; `start()`, `stop()`, `reset()` |
| `useTrajectory.js` | Derives bullet thoughts, adversary, ability names from a trajectory dict | reactive `trajectory` | `thoughts`, `adversary`, `abilityNames`, `splitSentences()`, `isInjectedSentence()` |

---

## Data flow (one prompt)

```
User types in ChatComposer
   │
   ▼  (submit event)
ChatWorkflow.handleSubmit()
   ├── push user message into messages[]
   ├── push assistant message (status='RUNNING') with a known id
   └── run.start(payload)              ← useMcpRun composable
                │
                ▼
       POST /plugin/mcp/execute        ← payload identical to legacy UI
                │
                ▼ (run_id returned)
       setInterval(GET /plugin/mcp/status, 1000ms)
                │
                ▼ (each tick)
       run.{status, stage, finalResult, reasoning, trajectory} updated
                │
                ▼ (watcher in ChatWorkflow)
       in-flight assistant message updated in place
                │
                ▼ (status === 'FINISHED' | 'FAILED')
       interval cleared, message frozen, composer re-enabled
```

The polling cadence and `/execute` payload are byte-for-byte identical to
the legacy view, so backend behavior is unchanged.

---

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ ChatSidebar (320px, collapsible)  │ Header: workflow name · status   │
│  ┌ Back                           ├──────────────────────────────────┤
│  │ Workflow title + description   │                                  │
│  │ ── Servers ──                  │                                  │
│  │ [✓] caldera_core               │   ChatTranscript                 │
│  │ ── Capabilities ──             │   (scrolling messages)           │
│  │ [✓] rag                        │                                  │
│  │ ── RAG Data ──                 │                                  │
│  │ TopK / embed model             │                                  │
│  │ Upload + file list             │                                  │
│  └                                │                                  │
│                                   ├──────────────────────────────────┤
│                                   │ ChatComposer                     │
│                                   │ [textarea ............ ] [send] │
└──────────────────────────────────────────────────────────────────────┘
                          height: calc(100vh - 80px)
```

---

## Theme

Dark palette to match the recent "match Result panel to the dark theme"
commit:

| Role | Color |
|------|-------|
| Background | `#14111f` (page), `#1a1726` (panels), `#1f1a2e` (assistant bubble) |
| Borders | `#3a3251`, `#2c2540` |
| Accent | `#b075ff` (purple), `#d8b8ff` (light purple for headings/strong) |
| Text | `#f5f5f5` (primary), `#ddd` (body), `#8a7fb0` (muted) |

The user-message bubble uses `#3a2c5e` to distinguish it from assistant
panels at a glance.

---

## What is *not* in this refactor

- **Multi-turn backend.** Each prompt still creates an isolated MLflow
  run. Sending a follow-up does not pass prior trajectory as context.
- **`plan_execute` workflow.** `public_mcp_ability_factory.vue` still
  uses the legacy single-page UI.
- **Run history page.** `mcp_history.vue` is unchanged.
- **Streaming.** Polling at 1 Hz is unchanged. No SSE, no WebSocket.

---

## Wiring changes

1. **`plugins/mcp/gui/views/mcp.vue`** — one-line import swap so the
   `author` workflow resolves to the new component:
   ```diff
   - import McpPromptFactory from './local_mcp_ability_factory.vue'
   + import McpPromptFactory from './chat/ChatWorkflow.vue'
   ```
   The `_BUILTIN_COMPONENTS` map still resolves both `author.vue` and
   the legacy alias `local_mcp_ability_factory.vue` through this import,
   so external plugins referencing the old component name keep working.

2. **`plugins/magma/src/main.js`** — three icons added to the FA library:
   `faAngleLeft`, `faPaperPlane`, `faChevronRight` (used by sidebar
   back, composer send, and thoughts toggle).

3. **`local_mcp_ability_factory.vue`** is still on disk (now unused).
   Keeping it for one cycle gives a trivial revert path; can be deleted
   in a follow-up once the chat UI has bake time.

---

## Backend contract (unchanged)

| Call | Shape | Notes |
|------|-------|-------|
| `POST /plugin/mcp/execute` | `{text, workflow_id, enabled_servers, enabled_capabilities, capability_settings, lm_config}` | Returns `{run_id}`; identical to legacy payload |
| `GET /plugin/mcp/status?run_id=…` | Returns `{status, stage, prompt, reasoning, process_result, trajectory}` | Polled at 1 Hz until `FINISHED`/`FAILED` |
| `POST /plugin/mcp/rag/upload`, `GET /plugin/mcp/rag/list` | Unchanged | Wired via `ChatSidebar` |

No new endpoints. No service-layer changes. No MLflow schema changes.

---

## Future work — true multi-turn (not in this PR)

If we want a continuation across turns sharing context (this is the
"backend NLP loop" half of the original question), the changes are:

| Layer | Change |
|-------|--------|
| API | New `POST /plugin/mcp/continue/{run_id}` taking `{text}` |
| Service | `mcp_svc._run_execution` learns to extend an existing session by passing prior trajectory (or compacted summary) into the next ReAct call |
| Workflow | Each `run()` accepts optional `prior_messages` and appends to its DSPy task signature |
| MLflow | Parent run per session (`session_id`, totals); child runs per turn (`parent_run_id`). New tags: `mcp.session_id`, `mcp.turn_index`, `mcp.parent_run_id` |
| Cache | `mcp_svc._runs` keyed by parent `run_id`; child run ids appended to a list in the parent's cache entry |
| Frontend | `useMcpRun` grows a `continueSession()` method that POSTs to `/continue` with the existing `run_id` |

The frontend module structure already supports this — only `useMcpRun.js`
and `ChatWorkflow.handleSubmit` would change.

---

## Build verification

- `node prebundle.js && vite build` (Node 22 from `caldera/caldera_node_env`)
  succeeds. Chat components are bundled into `dist/assets/mcp-*.js`.
- Caldera at `http://localhost:8888` serves the rebuilt bundle (HTTP 200,
  bundle contains `chat-workflow` / `composer-textarea` / `chat-transcript`
  class names).
- **Browser exercise has not been performed** — no chromium available in
  this venv. Required before declaring this done: submit an Author
  prompt, confirm running indicator + stage updates, expand thoughts,
  verify ability list + adversary card render.

---

## Reverting

If this design needs more iteration before landing:

```bash
# 1. Revert the single import line in mcp.vue
git checkout plugins/mcp/gui/views/mcp.vue
# 2. Revert the FA icon additions
git checkout plugins/magma/src/main.js
# 3. Remove the new chat module
rm -rf plugins/mcp/gui/views/chat/
# 4. Rebuild
cd plugins/magma && PATH=../../caldera_node_env/bin:$PATH node prebundle.js && ./node_modules/.bin/vite build
```

The legacy `local_mcp_ability_factory.vue` is still in place and becomes
the active component again after step 1.

---

## Open questions for review

1. **Sidebar default width** — 320px feels right on a 1440px display but
   may be cramped at 1280. Consider 280px or making it user-resizable.
2. **Empty-state copy** — currently "Type a prompt below to begin." Want
   a richer onboarding (example chips already render in the composer
   when the input is empty).
3. **Header "New chat" button** — clears transcript and resets state.
   Should it also write the cleared session to MLflow as abandoned, or
   silently drop it (current behavior)?
4. **Follow-up prompts today** — without backend multi-turn, follow-ups
   are independent runs. Should the UI surface this fact (e.g. a divider
   between independent runs) or hide it?
5. **Should `plan_execute` get the same treatment?** Easy to do once
   this design is validated; the modules are workflow-agnostic.
