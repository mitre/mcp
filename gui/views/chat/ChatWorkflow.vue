<!--
  Top-level chat-style page for a single MCP workflow. Owns the message
  transcript and a single in-flight run; each user prompt triggers one
  /plugin/mcp/execute call and appends the resulting assistant message to
  the transcript. The composer is disabled while a run is in progress.

  This component intentionally does not maintain a server-side session: the
  backend is still single-shot. The chat UI gives users a familiar Claude.ai
  shape today and provides the structural foundation for true multi-turn
  state once the backend grows a /continue endpoint.
-->
<template>
  <div ref="rootRef" class="chat-workflow">
    <main class="chat-main">
      <header class="chat-header">
        <div class="header-left">
          <button
            class="back-button"
            @click="$emit('back')"
            type="button"
            :disabled="run.isRunning.value"
            :title="run.isRunning.value
              ? 'Cannot leave while a run is in progress'
              : 'Back to workflow list'"
          >
            <font-awesome-icon :icon="['fas', 'angle-left']" />
            <span>Back</span>
          </button>
          <h2 class="header-title">{{ workflow?.display_name || 'MCP Workflow' }}</h2>
          <span v-if="run.isRunning.value" class="header-status running">
            <span class="status-dot"></span> Working
          </span>
          <span v-else-if="messages.length" class="header-status idle">
            {{ messages.filter(m => m.role === 'assistant').length }} response{{
              messages.filter(m => m.role === 'assistant').length === 1 ? '' : 's'
            }}
          </span>
        </div>
        <div class="header-right">
          <button
            v-if="supportsChatHistory"
            class="header-action history-toggle"
            :class="{ 'is-on': historyEnabled }"
            @click="historyEnabled = !historyEnabled"
            :disabled="run.isRunning.value"
            type="button"
            :title="historyEnabled
              ? 'Chat history is being threaded into each prompt. Click to disable for the rest of this session.'
              : 'Chat history is disabled for this session. Click to re-enable.'"
          >
            <span class="toggle-dot"></span>
            <span>History {{ historyEnabled ? 'on' : 'off' }}</span>
          </button>
          <button
            v-if="messages.length"
            class="header-action"
            @click="clearTranscript"
            :disabled="run.isRunning.value"
            type="button"
            title="Start a new chat"
          >
            <font-awesome-icon :icon="['fas', 'plus']" />
            <span>New chat</span>
          </button>
        </div>
      </header>

      <ChatTranscript
        :messages="messages"
        :workflow-name="workflow?.display_name"
        :workflow-description="workflow?.description"
        :split-sentences="splitSentences"
        :is-injected-sentence="isInjectedSentence"
      />

      <ChatComposer
        v-model="composerText"
        :disabled="run.isRunning.value"
        :example-prompts="examplePrompts"
        :placeholder="composerPlaceholder"
        @submit="handleSubmit"
      />
    </main>

    <ChatSidebar
      :workflow="workflow"
      :capabilities="capabilities"
      :available-servers="availableServers"
      :global-config="globalConfig"
      :$api="$api"
      v-model:selectedRag="selectedRag"
      :collapsed="sidebarCollapsed"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
    />
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import ChatSidebar from './ChatSidebar.vue'
import ChatTranscript from './ChatTranscript.vue'
import ChatComposer from './ChatComposer.vue'
import { useMcpRun } from './composables/useMcpRun.js'
import { useTrajectory } from './composables/useTrajectory.js'

const props = defineProps({
  workflow: { type: Object, default: () => ({}) },
  capabilities: { type: Array, default: () => [] },
})
defineEmits(['back'])

const $api = inject('$api')
const globalConfig = inject('mcpGlobalConfig')
const availableServers = inject('mcpAvailableServers', ref([]))

// --- UI state ---------------------------------------------------------------
const sidebarCollapsed = ref(false)
const composerText = ref('')
const selectedRag = ref([])
const messages = ref([])  // [{ id, role, text|finalResult, status, ... }]

// Server-assigned identifier for the current chat session. Null means the
// next prompt will start a fresh session; once set, follow-up prompts pass
// this value back so the backend threads accumulated chat history into the
// signature (only for workflows that opt in via supports_chat_history).
const sessionId = ref(null)

// True when the workflow has opted in to per-session chat history. Drives
// composer copy and the meaning of the "New chat" button. Defaults to false
// for safety if the field is missing from the workflow registration.
const supportsChatHistory = computed(() => !!props.workflow?.supports_chat_history)

// User-controlled session-wide override on top of the workflow flag.
// Defaults to ON for opt-in workflows; flipping it OFF turns the rest of
// the session into independent runs (no read of prior turns, no write of
// the new turn) until flipped back ON or the user clicks "New chat".
// Has no effect on workflows that opt out.
const historyEnabled = ref(true)
const historyActive = computed(
  () => supportsChatHistory.value && historyEnabled.value
)

// --- Viewport-fit -----------------------------------------------------------
// This view is full-screen (sidebar + chat fill the space between Caldera's
// outer chrome and the viewport bottom). Two things happen here:
//
// 1. Lock body overflow while mounted so Caldera never shows a page scrollbar
//    no matter what nests the chat. Restored on unmount.
// 2. Measure the chat's distance from the *document* top (rect.top + scrollY,
//    not just rect.top, so an in-flight page scroll doesn't skew the math) and
//    set height = calc(100vh - that). Re-runs on resize and once layout has
//    settled. Without this, a fixed offset like `100vh - 80px` is wrong on any
//    Caldera build whose chrome isn't exactly 80px tall.
const rootRef = ref(null)
let prevBodyOverflow = ''
let prevHtmlOverflow = ''

function syncHeight() {
  const el = rootRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const docTop = rect.top + (window.scrollY || window.pageYOffset || 0)
  el.style.height = `calc(100vh - ${Math.max(0, Math.round(docTop))}px)`
}

onMounted(() => {
  prevBodyOverflow = document.body.style.overflow
  prevHtmlOverflow = document.documentElement.style.overflow
  document.body.style.overflow = 'hidden'
  document.documentElement.style.overflow = 'hidden'
  // Two passes: once now (for the common case), once after the next paint to
  // catch late layout shifts (font load, parent reflow, etc.).
  nextTick(syncHeight)
  requestAnimationFrame(() => requestAnimationFrame(syncHeight))
  window.addEventListener('resize', syncHeight)
})
onBeforeUnmount(() => {
  document.body.style.overflow = prevBodyOverflow
  document.documentElement.style.overflow = prevHtmlOverflow
  window.removeEventListener('resize', syncHeight)
})

// --- Run lifecycle ----------------------------------------------------------
const run = useMcpRun($api)
const { thoughts, adversary, abilityNames, splitSentences, isInjectedSentence } =
  useTrajectory(run.trajectory)

// Sync the in-flight run into its assistant message as state changes. The
// assistant message is created at submit time with a known id; we update
// that message in place rather than re-pushing.
let pendingAssistantId = null
watch(
  () => ({
    status: run.status.value,
    stage: run.stage.value,
    finalResult: run.finalResult.value,
    reasoning: run.reasoning.value,
    err: run.errorMessage.value,
    trajKey: Object.keys(run.trajectory.value || {}).length,
  }),
  () => {
    if (!pendingAssistantId) return
    const msg = messages.value.find(m => m.id === pendingAssistantId)
    if (!msg) return
    msg.status = run.status.value
    msg.stage = run.stage.value
    msg.finalResult = run.finalResult.value
    msg.reasoning = run.reasoning.value
    msg.errorMessage = run.errorMessage.value
    msg.thoughts = thoughts.value
    msg.adversary = adversary.value
    msg.abilityNames = abilityNames.value
    if (msg.status === 'FINISHED' || msg.status === 'FAILED') {
      pendingAssistantId = null
    }
  },
  { deep: true }
)

// --- Workflow-derived UI bits ----------------------------------------------
const examplePrompts = computed(() => props.workflow?.example_prompts || [])
const composerPlaceholder = computed(() => {
  if (run.isRunning.value) return 'Working on the previous request…'
  if (messages.value.length) {
    if (historyActive.value) return 'Send a follow-up prompt in this session…'
    if (supportsChatHistory.value)
      return 'History is off for this session, each prompt runs independently…'
    return 'Send another prompt (each one runs independently)…'
  }
  return 'Describe what you want this workflow to do…'
})

// --- Submit -----------------------------------------------------------------
function _newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function handleSubmit() {
  const text = composerText.value?.trim()
  if (!text || run.isRunning.value) return

  const now = Date.now()
  messages.value.push({
    id: _newId(), role: 'user', text, timestamp: now,
  })

  const assistantId = _newId()
  pendingAssistantId = assistantId
  messages.value.push({
    id: assistantId,
    role: 'assistant',
    status: 'RUNNING',
    stage: '',
    finalResult: '',
    reasoning: '',
    thoughts: [],
    adversary: null,
    abilityNames: [],
    timestamp: now,
  })

  composerText.value = ''
  _startRun(text)
}

async function _startRun(text) {
  const filesAttached = selectedRag.value.length > 0
  const baseCaps = new Set(globalConfig.capabilitiesByWorkflow?.[props.workflow.id] || [])
  if (filesAttached) baseCaps.add('rag')

  const ragSettings = (globalConfig.capabilitySettings && globalConfig.capabilitySettings.rag) || {}

  const payload = {
    text,
    workflow_id: props.workflow.id,
    enabled_servers: globalConfig.serversByWorkflow?.[props.workflow.id] || [],
    enabled_capabilities: [...baseCaps],
    capability_settings: {
      rag: {
        rag_files: selectedRag.value,
        embed_model: ragSettings.embed_model || '',
        topk: ragSettings.topk,
      },
    },
    lm_config: {
      model: globalConfig.modelName,
      temperature: globalConfig.temperature,
      api_key: globalConfig.apiKey,
      max_tool_calls: globalConfig.maxToolCalls,
      max_tokens: globalConfig.maxTokens,
    },
    // Null on the very first turn of a session; the backend assigns one
    // and the response echoes it back. Subsequent turns pass it so the
    // backend threads accumulated chat history (opt-in workflows only).
    session_id: sessionId.value,
    // True only when the user has flipped the header toggle off mid-
    // session. The backend already gates on workflow opt-in, so sending
    // false here is the no-op default for workflows that don't support
    // history at all.
    disable_history: supportsChatHistory.value && !historyEnabled.value,
  }

  try {
    const resp = await run.start(payload)
    if (resp?.session_id && !sessionId.value) {
      sessionId.value = resp.session_id
    }
  } catch {
    // run.errorMessage is already populated by useMcpRun.
  }
}

function clearTranscript() {
  if (run.isRunning.value) return
  // For opt-in workflows the session id is what the server uses to look
  // up accumulated history. Clearing the transcript means starting a
  // fresh conversation, so drop the session id too. Single-shot
  // workflows reset the same field; it just had no semantic meaning
  // for them.
  messages.value = []
  sessionId.value = null
  // Reset the per-session history toggle to its default (on). For
  // opt-out workflows this has no visible effect since the toggle is
  // not rendered.
  historyEnabled.value = true
  run.reset()
  pendingAssistantId = null
}
</script>

<style scoped>
.chat-workflow {
  display: flex;
  width: 100%;
  /* height set imperatively from syncHeight() so the chat fills exactly the
     space between its top edge and the viewport bottom — no page scroll. */
  height: 100vh;
  color: #f5f5f5;
  overflow: hidden;
  border-left: 1px solid #3a3a3a;
}
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* Tight vertical padding so the header strip feels like a thin top
     bar rather than a chunky chrome row. The 28px controls inside
     dominate the height. */
  padding: 0.5rem 1.6rem;
  background-color: #1f1f1f;
  border-bottom: 1px solid #3a3a3a;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  /* Centred so the row has even padding above and below. With both
     items locked to the same 28px height and matching line-height: 1
     the small baseline mismatch from differing font sizes is under
     2px, which is below the visual threshold; what the eye notices
     is asymmetric padding around the row, not sub-pixel baselines. */
  align-items: center;
  gap: 0.85rem;
}
.back-button {
  /* Same fixed height as the collapse-toggle in the sidebar header so
     both top-bar strips end at the exact same Y. */
  height: 28px;
  background: transparent;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  color: #888888;
  cursor: pointer;
  font-size: 0.82rem;
  line-height: 1;
  padding: 0 0.7rem 0 0.55rem;
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}
.back-button:hover:not(:disabled) {
  color: #d0d0d0;
  background-color: rgba(255, 255, 255, 0.05);
  border-color: #555555;
}
.back-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.header-title {
  /* Same 28px box as .back-button so the text inside both boxes lands
     on the same horizontal centerline. */
  height: 28px;
  display: inline-flex;
  align-items: center;
  font-size: 1.1rem;
  font-weight: 600;
  line-height: 1;
  color: #d0d0d0;
  margin: 0;
}
.header-status {
  font-size: 0.78rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
}
.header-status.running {
  color: #888888;
  background-color: rgba(255, 255, 255, 0.06);
}
.header-status.idle {
  color: #888888;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: #888888;
  animation: blink 1.4s infinite ease-in-out;
}
@keyframes blink {
  0%, 100% { opacity: 0.35; }
  50%      { opacity: 1; }
}
.header-action {
  background-color: transparent;
  color: #d0d0d0;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  padding: 0.4rem 0.75rem;
  font-size: 0.82rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.header-action:hover:not(:disabled) {
  background-color: rgba(255, 255, 255, 0.05);
  border-color: #888888;
}
.header-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.history-toggle {
  /* Off state: muted grey, blends into the header. Subtle by design so
     people aren't constantly drawn to it. */
  color: #888888;
  border-color: #3a3a3a;
}
.history-toggle.is-on {
  /* On state: slightly lifted background + brighter text so the user
     can tell at a glance that history threading is active. */
  color: #d0d0d0;
  background-color: rgba(255, 255, 255, 0.04);
  border-color: #555555;
}
.toggle-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #555555;
  display: inline-block;
}
.history-toggle.is-on .toggle-dot {
  background-color: #d0d0d0;
}
</style>
