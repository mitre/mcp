# Multi-Turn Chat Plan — Layered History in a Single Session

**Status:** Plan only. Nothing implemented yet. Created alongside the
existing UI redesign so the two phases can be reviewed independently.

**Goal.** When the user sends prompt N in a chat against a workflow
that benefits from continuity, the LLM sees prompts 1..N-1 and their
assistant responses as context. Existing single-shot callers (no
`session_id`) keep working unchanged.

**Approach in one sentence.** Add a `session_id` to the request /
response, accumulate `(prompt, response)` turns in a server-side
session store keyed by it, and thread that history into the DSPy
signature as a new `chat_history` input field — but **only for
workflows that opt in**.

---

## Why opt-in (not blanket)

Not every workflow benefits from chat history, and history that adds
no value still costs tokens.

- **Author** workflow is essentially atomic per turn. Each artifact is
  fully described in the prompt, and "now do another like it" can be
  re-derived by re-listing existing abilities. History adds tokens
  without adding signal. → **Stays single-shot.**
- **Plan & Execute** and any **infrastructure / range provisioning**
  workflows produce *entities with ids* (instances, profiles, deploys)
  that subsequent turns need to reference. "Add this feature to the
  instance I just made" is unanswerable without history. → **Opts in.**

The flag lives on the workflow registration, so third-party plugin
workflows decide for themselves.

---

## Components & ordered changes

### 0. Workflow opt-in flag
[workflows/base.py:25](plugins/mcp/app/workflows/base.py#L25)

Add one boolean to the `Workflow` dataclass:

```python
# Whether this workflow benefits from prior-turn context. When True,
# the orchestrator threads accumulated `(prompt, process_result)`
# pairs from the same session into the signature's `chat_history`
# input. When False, every turn runs single-shot — the chat UI still
# shows past turns visually, but the LLM sees a fresh context each time.
supports_chat_history: bool = False
```

Built-in registrations:
- `author`: stays at default `False`.
- `plan_execute`: set to `True`.

The `/plugin/mcp/workflows` API surfaces this flag so the frontend can
adapt affordances per workflow.

### 1. DSPy signatures (only for opt-in workflows)
[workflows/plan_execute.py:88](plugins/mcp/app/workflows/plan_execute.py#L88)

Add one new InputField to the opt-in signatures:

```python
chat_history: str = dspy.InputField(
    desc="Prior turns in this conversation, oldest first. Each turn is "
         "labelled 'User:' / 'Assistant:'. Use them to resolve follow-up "
         "references like 'those abilities' or 'the one I just created'. "
         "Empty string on the first turn."
)
```

Plain `str` instead of `dspy.History` — version-agnostic and
predictable formatting.

### 2. Workflow `run()` functions

Opt-in workflows' `run()` definitions gain a `chat_history: str = ""`
parameter. Pass it to:

```python
react.acall(
    adversary_emulation_task=...,
    chat_history=chat_history,
)
```

Single-shot workflows (Author) are unchanged.

### 3. Service layer
[mcp_svc.py](plugins/mcp/app/mcp_svc.py)

- Add `self._sessions: OrderedDict[str, list[Turn]]` where
  `Turn = {"prompt": str, "response": str}`. LRU-bounded (e.g., 64
  sessions).
- `_run_execution` learns to:
  - Read `session_id` from the request.
  - **If the workflow has `supports_chat_history=False`**, ignore the
    session_id entirely (no accumulation, no threading) — the field
    becomes a no-op for those workflows.
  - **If the workflow opts in**: format the session's turns into a
    single `chat_history` string, pass it to `run()`, and on
    completion append the new `(prompt, process_result)` turn to the
    session's list.
- Cap session length: keep the last **8 turns**, drop oldest. Stops
  uncontrolled token growth without compaction logic in v1.
- The `session_id` IS the first turn's `run_id` — no separate UUID
  generation. Subsequent runs in the same session each get their own
  `run_id` but share `session_id`.

### 4. API layer
[mcp_api.py](plugins/mcp/app/mcp_api.py)

- `POST /plugin/mcp/execute` accepts optional `session_id` in the
  body. If absent → starts a new session, returns
  `{run_id, session_id: run_id}`. If present → continues that
  session, returns `{run_id, session_id}`.
- No new endpoint needed. The shape stays additive and
  backward-compatible.

### 5. MLflow — minimal

Tag every run with `mcp.session_id` and `mcp.turn_index`. That's it —
no parent/child run hierarchy in v1. The MLflow UI lets you filter by
tag, which is enough to view a session's runs together.

### 6. Frontend
[ChatWorkflow.vue](plugins/mcp/gui/views/chat/ChatWorkflow.vue),
[useMcpRun.js](plugins/mcp/gui/views/chat/composables/useMcpRun.js)

- `ChatWorkflow` adds `const sessionId = ref(null)`.
- `handleSubmit` sends `session_id: sessionId.value` (null on first
  turn).
- On the response, if `sessionId.value` is null, set it to the
  returned `session_id`.
- `clearTranscript` (the "New chat" button) resets
  `sessionId.value = null`. Next prompt starts a fresh session.
- `useMcpRun.start(payload)` — no shape change. `payload` already
  passes through.
- **Per-workflow affordances** based on
  `workflow.supports_chat_history`:
  - **Opt-in workflows** (Plan & Execute, Range, etc.): composer
    placeholder reads "Send a follow-up prompt…" after the first
    turn. "New chat" button has stronger meaning ("start fresh
    context").
  - **Single-shot workflows** (Author): composer placeholder stays
    "Describe what you want this workflow to do…" between turns.
    Each prompt is independent and the user should be reminded —
    consider a small subtitle like "Each prompt runs independently"
    near the header.

---

## What stays exactly the same

- Polling (`/status`) is unchanged.
- Per-turn trajectory in the UI is unchanged — each turn still has
  its own thoughts/reasoning panel.
- RAG fetches per turn (not carried across) — RAG context is
  task-specific, not conversational.
- Workflow registry, capability registry, server registry —
  untouched.
- The `plan_execute` workflow's two-phase translator is untouched
  (history threads in, but plan validation logic stays as-is).
- All existing API consumers that don't pass `session_id` continue to
  work as single-shot.

---

## Decisions worth sign-off

| # | Decision | Default |
|---|----------|---------|
| 1 | History field type | `str` (simple, predictable) over `dspy.History` (version-tied) |
| 2 | History cap | Last **8 turns**, drop oldest. Token-budget + summarization is v2. |
| 3 | What goes into history | User prompt + final `process_result` only. Tool calls / reasoning trajectories stay scoped to their own turn. (Including trajectories blows up token use fast and rarely improves the next turn.) |
| 4 | Session storage | In-memory dict on the service. Lost on restart. MLflow tags let you reconstruct a session by querying `mcp.session_id` if needed. |
| 5 | Scope | **Opt-in per workflow.** Author stays single-shot; plan_execute opts in. Range and other infra workflows opt in when added — they're the ones with cross-turn entity continuity needs. |

---

## Open UX question

Should the "New chat" header button explicitly call out "this clears
context"? Right now it just clears the transcript. With history layered
in, that button takes on a stronger meaning. A small confirmation
("Start a new chat? Current context will be cleared.") might be worth
it.

---

## Out of scope (intentionally)

- True parent/child MLflow run hierarchy. Tags are enough for v1.
- Token-budget-aware compaction / summarization of older turns.
- Cross-restart persistence (would need a DB or MLflow round-trip).
- Streaming the assistant response token-by-token. Polling still wins
  on simplicity and matches existing infra.
- Concurrent in-flight turns per session. The composer is disabled
  during a run, so this never arises in the UI; the service can stay
  single-in-flight per session.
- Multi-turn for any third-party plugin's custom workflow that
  doesn't use the shared signatures. Those workflows can opt in by
  adding their own `chat_history` field.

---

## Rollout / verification

1. Land backend changes (signatures, `run()`, service, API) behind
   the `session_id`-optional contract — existing UI keeps working.
2. Manually exercise via `curl`: two POSTs with the same
   `session_id`, confirm the second response demonstrates awareness
   of the first.
3. Land frontend changes. Verify visually: send "create an ability
   that runs ls", then "now wrap that into an adversary called Foo"
   — second prompt should reference the ability from the first
   without re-stating the id.
4. Verify MLflow: filter `mcp.session_id = <id>`, see two runs with
   `mcp.turn_index = 0` and `1`.
5. Verify backward compat: a request without `session_id` still
   returns a `run_id` and behaves as a one-shot.

---

## Reverting

Changes are purely additive (new optional field, new optional
parameter, new service state). Reverting means:

1. Drop the `chat_history` InputField from both signatures.
2. Drop the `chat_history` parameter from both `run()` functions.
3. Drop `_sessions` and the session logic from `mcp_svc`.
4. Drop the `session_id` body field from `/execute`.
5. Drop `sessionId` from `ChatWorkflow.vue`.

Each step is a few lines. No data loss — sessions are in-memory.
