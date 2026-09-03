// Per-workflow chat session state, persisted to localStorage.
//
// Why this exists:
//   ChatWorkflow.vue mounts and unmounts whenever the user clicks Back
//   to the landing page and then re-enters a workflow card. All in-
//   component refs (messages, sessionId, composer text, attachedIntel,
//   historyEnabled) reset on each mount, so the user perceives a fresh
//   session every time. The backend already keys chat history by a
//   server-assigned session_id, so the only thing missing on the client
//   is durable storage for that id and the rendered transcript.
//
// What it owns:
//   For one (workflow_id), this composable owns four pieces of state:
//     - messages           the transcript shown in ChatTranscript
//     - sessionId          the server-assigned id paired with this
//                          conversation; null only for a brand-new chat
//     - historyEnabled     whether the next turn passes prior history
//                          to the LLM (only meaningful for opt-in
//                          workflows)
//     - attachedIntel      which CTI bundles are attached to
//                          the next prompt
//
// What it does not own:
//   composerText, transient run-state (status/stage/finalResult on the
//   in-flight assistant message). Composer text is intentionally not
//   persisted: half-typed prompts surviving a remount is a worse UX
//   than a clean text box. In-flight run state belongs to useMcpRun and
//   is reconstructed from the polling endpoint; localStorage only keeps
//   the run_id needed to ask for it again.
//
// Storage shape:
//   localStorage key 'mcp_chat_sessions' holds:
//     { schema: 1, workflows: { <workflow_id>: { messages, sessionId,
//                                                historyEnabled,
//                                                attachedIntel,
//                                                updated_at } } }
//   The schema version lets future changes drop incompatible blobs
//   without confusing rehydration.
//
// Assistant messages carry their run_id, so a bubble left mid-run survives
// a remount and ChatWorkflow re-attaches a poller to it. Older RUNNING
// messages, and any with no run_id, are failed on hydrate: nothing is going
// to move them again.
//
// Limits:
//   Per-workflow caps at MAX_MESSAGES messages and MAX_BYTES total
//   serialized size. Older messages are dropped first. localStorage
//   is typically 5–10 MB per origin; we stay well under that.

import { ref, watch } from 'vue'

const STORAGE_KEY = 'mcp_chat_sessions'
const SCHEMA_VERSION = 1
const MAX_MESSAGES = 200
const MAX_BYTES = 750_000  // ~750 KB per workflow keeps us safely under quota

function _readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { schema: SCHEMA_VERSION, workflows: {} }
    const parsed = JSON.parse(raw)
    if (parsed?.schema !== SCHEMA_VERSION || !parsed.workflows) {
      // Schema mismatch: drop the old blob rather than risk hydrating
      // it into an incompatible component.
      return { schema: SCHEMA_VERSION, workflows: {} }
    }
    return parsed
  } catch (e) {
    console.warn('[MCP] Failed to read chat sessions:', e)
    return { schema: SCHEMA_VERSION, workflows: {} }
  }
}

function _writeAll(blob) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(blob))
  } catch (e) {
    console.warn('[MCP] Failed to persist chat sessions:', e)
  }
}

function _readWorkflow(workflowId) {
  const all = _readAll()
  return all.workflows[workflowId] || null
}

function _writeWorkflow(workflowId, slice) {
  const all = _readAll()
  all.workflows[workflowId] = { ...slice, updated_at: Date.now() }
  _writeAll(all)
}

function _trimMessages(messages) {
  // Cap by count first (cheap), then by serialized size (defensive).
  let trimmed = messages.length > MAX_MESSAGES
    ? messages.slice(messages.length - MAX_MESSAGES)
    : messages
  while (trimmed.length > 1 && JSON.stringify(trimmed).length > MAX_BYTES) {
    trimmed = trimmed.slice(1)
  }
  return trimmed
}

function _markUnresumableRunning(messages) {
  // Only the newest RUNNING message can be re-attached; the view polls one
  // run at a time. A bubble left frozen on "Thinking" would lie to the user.
  const resumableIndex = messages.reduce(
    (last, m, i) => (m.status === 'RUNNING' && m.runId ? i : last),
    -1
  )
  return messages.map((m, i) => {
    if (m.status !== 'RUNNING' || i === resumableIndex) return m
    return {
      ...m,
      status: 'FAILED',
      stage: '',
      errorMessage:
        m.errorMessage
        || 'The page stopped tracking this run. '
           + 'Check the History tab for the final result.',
    }
  })
}

export function useChatSession(workflowId) {
  const messages = ref([])
  const sessionId = ref(null)
  const historyEnabled = ref(true)
  const attachedIntel = ref([])

  function hydrate() {
    const slice = _readWorkflow(workflowId)
    if (!slice) return
    messages.value = _markUnresumableRunning(slice.messages || [])
    sessionId.value = slice.sessionId ?? null
    historyEnabled.value =
      typeof slice.historyEnabled === 'boolean' ? slice.historyEnabled : true
    attachedIntel.value = Array.isArray(slice.attachedIntel) ? slice.attachedIntel : []
  }

  function persist() {
    _writeWorkflow(workflowId, {
      messages: _trimMessages(messages.value),
      sessionId: sessionId.value,
      historyEnabled: historyEnabled.value,
      attachedIntel: attachedIntel.value,
    })
  }

  // Persist on any change. deep:true catches in-place message mutation
  // (status, finalResult, errorMessage updates from useMcpRun's watcher).
  watch(
    [messages, sessionId, historyEnabled, attachedIntel],
    persist,
    { deep: true }
  )

  function reset() {
    // Explicit "New chat": wipe both memory and disk for this workflow.
    messages.value = []
    sessionId.value = null
    historyEnabled.value = true
    attachedIntel.value = []
    const all = _readAll()
    delete all.workflows[workflowId]
    _writeAll(all)
  }

  return {
    messages,
    sessionId,
    historyEnabled,
    attachedIntel,
    hydrate,
    // For the one write that cannot wait for the watcher: a run_id arriving
    // after unmount, once the scope holding that watcher is stopped.
    persist,
    reset,
  }
}
