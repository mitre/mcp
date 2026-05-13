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
      <section class="workflow-intro">
        <h1 class="workflow-intro-title">{{ workflow?.display_name || 'MCP Workflow' }}</h1>
        <p v-if="workflow?.description" class="workflow-intro-desc">
          {{ workflow.description }}
        </p>
      </section>

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
            <font-awesome-icon :icon="backIcon" />
            <span>Back</span>
          </button>
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
            <font-awesome-icon :icon="plusIcon" />
            <span>New chat</span>
          </button>
        </div>
      </header>

      <ChatTranscript
        :messages="messages"
        :workflow-name="workflow?.display_name"
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
      v-model:selectedRag="selectedRag"
      v-model:workflowContext="workflowContext"
      :collapsed="sidebarCollapsed"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
    />
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { faAngleLeft, faPlus } from '@fortawesome/free-solid-svg-icons'
import ChatSidebar from './ChatSidebar.vue'
import ChatTranscript from './ChatTranscript.vue'
import ChatComposer from './ChatComposer.vue'
import { useMcpRun } from './composables/useMcpRun.js'
import { useTrajectory } from './composables/useTrajectory.js'
import { useChatSession } from './composables/useChatSession.js'

const props = defineProps({
  workflow: { type: Object, default: () => ({}) },
  capabilities: { type: Array, default: () => [] },
})
defineEmits(['back'])

const $api = inject('$api')
const globalConfig = inject('mcpGlobalConfig')
const availableServers = inject('mcpAvailableServers', ref([]))
const backIcon = faAngleLeft
const plusIcon = faPlus

// --- Persistent per-workflow chat state -------------------------------------
// useChatSession owns messages / sessionId / historyEnabled / selectedRag
// and persists them to localStorage keyed by workflow.id. Hydrates once on
// mount so leaving the view and coming back re-renders the same transcript;
// reset() is the only path that wipes them (called by clearTranscript).
//
// composerText is intentionally NOT persisted: a half-typed prompt
// surviving a remount is a worse UX than a clean text box.
const session = useChatSession(props.workflow.id || '__default__')
const messages = session.messages
const sessionId = session.sessionId
const historyEnabled = session.historyEnabled
const selectedRag = session.selectedRag

// --- UI state ---------------------------------------------------------------
const sidebarCollapsed = ref(false)
const composerText = ref('')
const workflowContext = ref({})

// True when the workflow has opted in to per-session chat history. Drives
// composer copy and the meaning of the "New chat" button. Defaults to false
// for safety if the field is missing from the workflow registration.
const supportsChatHistory = computed(() => !!props.workflow?.supports_chat_history)

// historyEnabled is owned by the session composable above so the user's
// choice survives navigating away. The convenience computed below mirrors
// the legacy contract: true only when the workflow opts in AND the user
// has not flipped the toggle off.
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
  // Bring saved transcript / sessionId / historyEnabled / selectedRag back
  // before the first render pass. Has to happen before the height sync so
  // the transcript scroll position settles correctly on a hydrated view.
  session.hydrate()

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
  const context = workflowContext.value || {}
  const selectedCtiFiles = Array.isArray(context.selected_stix_files)
    ? context.selected_stix_files
    : []
  const ragFiles = [...new Set([...(selectedRag.value || []), ...selectedCtiFiles])]
  const filesAttached = ragFiles.length > 0
  const baseCaps = new Set(globalConfig.capabilitiesByWorkflow?.[props.workflow.id] || [])
  if (filesAttached) baseCaps.add('rag')
  const baseServers = new Set(globalConfig.serversByWorkflow?.[props.workflow.id] || [])
  if (props.workflow?.id === 'plan_execute' && selectedCtiFiles.length) {
    baseServers.add('cti_pipeline')
  }

  const ragSettings = (globalConfig.capabilitySettings && globalConfig.capabilitySettings.rag) || {}
  const inferredCtiRag = props.workflow?.id === 'plan_execute' && selectedCtiFiles.length > 0
  const ctiRagModel = typeof context.cti_rag_model === 'string'
    ? context.cti_rag_model.trim()
    : ''
  const ctiRagApiBase = typeof context.cti_rag_api_base === 'string'
    ? context.cti_rag_api_base.trim()
    : ''
  const ctiRagApiKey = typeof context.cti_rag_api_key === 'string'
    ? context.cti_rag_api_key
    : ''
  const ragModel = inferredCtiRag
    ? (ctiRagModel || ragSettings.embed_model || globalConfig.modelName || '')
    : (ragSettings.embed_model || '')
  const ragApiBase = inferredCtiRag
    ? (ctiRagApiBase || globalConfig.apiBase || '')
    : (ragSettings.embed_api_base || ragSettings.api_base || globalConfig.apiBase || '')
  const ragApiKey = inferredCtiRag
    ? (ctiRagApiKey || globalConfig.apiKey || '')
    : (ragSettings.embed_api_key || ragSettings.api_key || globalConfig.apiKey || '')
  const ragTopk = inferredCtiRag
    ? (context.cti_rag_topk || ragSettings.topk)
    : ragSettings.topk

  const payload = {
    text,
    workflow_id: props.workflow.id,
    enabled_servers: [...baseServers],
    enabled_capabilities: [...baseCaps],
    capability_settings: {
      rag: {
        rag_files: ragFiles,
        embed_model: ragModel,
        embed_api_base: ragApiBase,
        embed_api_key: ragApiKey,
        api_base: ragApiBase,
        api_key: ragApiKey,
        temperature: inferredCtiRag ? context.cti_rag_temperature : ragSettings.temperature,
        max_tool_calls: inferredCtiRag ? context.cti_rag_max_tool_calls : ragSettings.max_tool_calls,
        max_tokens: inferredCtiRag ? context.cti_rag_max_tokens : ragSettings.max_tokens,
        topk: ragTopk,
      },
    },
    lm_config: {
      model: globalConfig.modelName,
      temperature: globalConfig.temperature,
      api_base: globalConfig.apiBase,
      api_key: globalConfig.apiKey,
      max_tool_calls: globalConfig.maxToolCalls,
      max_tokens: globalConfig.maxTokens,
    },
    workflow_context: context,
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
  // "New chat" is the only path that wipes durable session state. The
  // composable resets messages, sessionId, historyEnabled, and
  // selectedRag in memory AND removes this workflow's slice from
  // localStorage so a future remount starts genuinely fresh. For
  // opt-in workflows this also tells the server to forget the prior
  // session_id (it's the keying field the backend uses to look up
  // accumulated chat history); single-shot workflows reset the same
  // fields, they just have no semantic meaning for them.
  session.reset()
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
  border-left: 1px solid rgba(158, 98, 255, 0.22);
}
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.workflow-intro {
  flex-shrink: 0;
  padding: 1.25rem 1.6rem 1rem 1.6rem;
  width: 100%;
  box-sizing: border-box;
  background:
    linear-gradient(180deg, rgba(139, 92, 246, 0.12), rgba(23, 19, 31, 0.88)),
    #17131f;
  border-bottom: 1px solid rgba(158, 98, 255, 0.28);
}
.workflow-intro-title {
  font-size: 1.28rem;
  line-height: 1.15;
  font-weight: 650;
  color: #f3efff;
  margin: 0 0 0.42rem 0;
}
.workflow-intro-desc {
  width: 100%;
  max-width: none;
  font-size: 0.92rem;
  line-height: 1.5;
  color: #d8d1e8;
  margin: 0;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* Tight vertical padding so the header strip feels like a thin top
     bar rather than a chunky chrome row. The 28px controls inside
     dominate the height. */
  padding: 0.5rem 1.6rem;
  background-color: #17131f;
  border-bottom: 1px solid rgba(158, 98, 255, 0.24);
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
.header-right {
  /* Explicit horizontal flex with a fixed gap so the History toggle
     and New chat button sit side-by-side with consistent spacing,
     instead of relying on each button's display value to do it. */
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.back-button {
  /* Same fixed height as the collapse-toggle in the sidebar header so
     both top-bar strips end at the exact same Y. Matches the
     header-title's font-size so the two read on the same horizontal
     line; visual hierarchy comes from font-weight and the muted
     colour, not from a smaller font. */
  height: 28px;
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid rgba(169, 112, 255, 0.28);
  border-radius: 6px;
  color: #cfc3ff;
  cursor: pointer;
  font-size: 0.95rem;
  font-weight: 500;
  line-height: 1;
  padding: 0 0.7rem 0 0.55rem;
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  transition: color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease;
}
.back-button:hover:not(:disabled) {
  color: #ffffff;
  background-color: rgba(169, 112, 255, 0.16);
  border-color: #a970ff;
}
.back-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.header-status {
  font-size: 0.78rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  border: 1px solid transparent;
}
.header-status.running {
  color: #ffe7b8;
  background-color: rgba(245, 158, 11, 0.13);
  border-color: rgba(245, 158, 11, 0.42);
}
.header-status.idle {
  color: #c9b8ff;
  background-color: rgba(139, 92, 246, 0.12);
  border-color: rgba(169, 112, 255, 0.28);
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.16);
  animation: blink 1.4s infinite ease-in-out;
}
@keyframes blink {
  0%, 100% { opacity: 0.35; }
  50%      { opacity: 1; }
}
.header-action {
  /* inline-flex so multiple actions sit side-by-side as siblings;
     plain `display: flex` would make each button block-level and the
     two buttons would stack vertically. */
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background-color: rgba(139, 92, 246, 0.08);
  color: #d8d1e8;
  border: 1px solid rgba(169, 112, 255, 0.28);
  border-radius: 6px;
  padding: 0.4rem 0.75rem;
  font-size: 0.82rem;
  cursor: pointer;
}
.header-action:hover:not(:disabled) {
  background-color: rgba(169, 112, 255, 0.16);
  border-color: #a970ff;
  color: #ffffff;
}
.header-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.history-toggle {
  /* Off state: muted grey, blends into the header. Subtle by design so
     people aren't constantly drawn to it. */
  color: #a99dbe;
  border-color: rgba(169, 112, 255, 0.22);
}
.history-toggle.is-on {
  /* On state: slightly lifted background + brighter text so the user
     can tell at a glance that history threading is active. */
  color: #dcfff0;
  background-color: rgba(45, 212, 191, 0.13);
  border-color: rgba(45, 212, 191, 0.48);
}
.toggle-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #6b607a;
  display: inline-block;
}
.history-toggle.is-on .toggle-dot {
  background-color: #2dd4bf;
  box-shadow: 0 0 0 3px rgba(45, 212, 191, 0.15);
}
</style>
