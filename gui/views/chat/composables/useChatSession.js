// Per-workflow chat session state, persisted to localStorage.
//
// Why this exists:
//   ChatWorkflow.vue mounts and unmounts whenever the user clicks Back
//   to the landing page and then re-enters a workflow card. All in-
//   component refs (messages, sessionId, composer text, selectedRag,
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
//     - selectedRag        which uploaded RAG files are attached to
//                          the next prompt
//
// What it does not own:
//   composerText, transient run-state (status/stage/finalResult on the
//   in-flight assistant message). Composer text is intentionally not
//   persisted — half-typed prompts surviving a remount is a worse UX
//   than a clean text box. In-flight run state belongs to useMcpRun
//   and is reconstructed from the polling endpoint, not localStorage.
//
// Storage shape:
//   localStorage key 'mcp_chat_sessions' holds:
//     { schema: 1, workflows: { <workflow_id>: { messages, sessionId,
//                                                historyEnabled,
//                                                selectedRag,
//                                                updated_at } } }
//   The schema version lets future changes drop incompatible blobs
//   without confusing rehydration.
//
// On hydrate the composable also marks any message whose status is
// still 'RUNNING' as FAILED with a "polling stopped" note. Polling
// timers do not survive a component unmount; leaving the bubble
// frozen on "Thinking" forever is misleading. The MLflow run is still
// findable via the History tab if the user needs the result.
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

function _markStaleRunningAsFailed(messages) {
  // A polling timer cannot survive a component unmount. Any message
  // that was RUNNING when we last saved is no longer being updated;
  // surfacing the stale state would lie to the user. Mark it FAILED
  // with a hint so the user knows where to look (History tab).
  return messages.map(m => {
    if (m.status === 'RUNNING') {
      return {
        ...m,
        status: 'FAILED',
        stage: '',
        errorMessage:
          m.errorMessage
          || 'Polling stopped when you navigated away. '
             + 'Check the History tab for the final result.',
      }
    }
    return m
  })
}

export function useChatSession(workflowId) {
  const messages = ref([])
  const sessionId = ref(null)
  const historyEnabled = ref(true)
  const selectedRag = ref([])

  function hydrate() {
    const slice = _readWorkflow(workflowId)
    if (!slice) return
    messages.value = _markStaleRunningAsFailed(slice.messages || [])
    sessionId.value = slice.sessionId ?? null
    historyEnabled.value =
      typeof slice.historyEnabled === 'boolean' ? slice.historyEnabled : true
    selectedRag.value = Array.isArray(slice.selectedRag) ? slice.selectedRag : []
  }

  function persist() {
    _writeWorkflow(workflowId, {
      messages: _trimMessages(messages.value),
      sessionId: sessionId.value,
      historyEnabled: historyEnabled.value,
      selectedRag: selectedRag.value,
    })
  }

  // Persist on any change. deep:true catches in-place message mutation
  // (status, finalResult, errorMessage updates from useMcpRun's watcher).
  watch(
    [messages, sessionId, historyEnabled, selectedRag],
    persist,
    { deep: true }
  )

  function reset() {
    // Explicit "New chat": wipe both memory and disk for this workflow.
    messages.value = []
    sessionId.value = null
    historyEnabled.value = true
    selectedRag.value = []
    const all = _readAll()
    delete all.workflows[workflowId]
    _writeAll(all)
  }

  return {
    messages,
    sessionId,
    historyEnabled,
    selectedRag,
    hydrate,
    reset,
  }
}
