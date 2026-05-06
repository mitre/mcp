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
      @back="$emit('back')"
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
  if (messages.value.length) return 'Send a follow-up prompt…'
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

function _startRun(text) {
  // Mirror the legacy payload shape from local_mcp_ability_factory.vue so
  // backend behavior is identical to the old single-shot UI.
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
  }

  run.start(payload).catch(() => { /* errorMessage already populated */ })
}

function clearTranscript() {
  if (run.isRunning.value) return
  messages.value = []
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
  padding: 0.85rem 1.6rem;
  background-color: #1f1f1f;
  border-bottom: 1px solid #3a3a3a;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}
.header-title {
  font-size: 1.1rem;
  font-weight: 600;
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
</style>
