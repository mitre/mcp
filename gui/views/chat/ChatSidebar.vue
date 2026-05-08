<!--
  Collapsible left rail with workflow-scoped configuration: enabled MCP
  servers, capabilities, and (when this workflow accepts the rag
  capability) the RAG file picker. RAG concerns are owned by
  ChatRagPanel; this file is purely the server/capability checklists
  plus chrome.

  All state is read/written through globalConfig keyed by workflow.id —
  the same contract the legacy view used.
-->
<template>
  <aside class="chat-sidebar" :class="{ collapsed }">
    <header class="sidebar-header">
      <button class="collapse-toggle" @click="$emit('toggle')" type="button"
              :title="collapsed ? 'Expand panel' : 'Collapse panel'">
        <font-awesome-icon :icon="['fas', collapsed ? 'angle-left' : 'angle-right']" />
      </button>
    </header>

    <div v-if="!collapsed" class="sidebar-body">
      <h3 class="sidebar-title">{{ workflow?.display_name || 'Workflow' }}</h3>
      <p v-if="workflow?.description" class="sidebar-desc">
        {{ workflow.description }}
      </p>

      <Section title="Servers" v-if="serverChoices.length">
        <label
          v-for="srv in serverChoices"
          :key="srv.name"
          class="check-row"
          :title="srv.description"
        >
          <input
            type="checkbox"
            :checked="enabledServers.includes(srv.name)"
            :disabled="srv.required"
            @change="toggleServer(srv.name, $event.target.checked)"
          />
          <span class="check-name">{{ srv.display_name }}</span>
          <span class="check-meta">
            {{ srv.name }}<span v-if="srv.required"> · required</span>
          </span>
        </label>
      </Section>

      <Section title="Capabilities" v-if="capabilityChoices.length">
        <label
          v-for="cap in capabilityChoices"
          :key="cap.id"
          class="check-row"
          :title="cap.description"
        >
          <input
            type="checkbox"
            :checked="enabledCapabilities.includes(cap.id)"
            @change="toggleCapability(cap.id, $event.target.checked)"
          />
          <span class="check-name">{{ cap.display_name }}</span>
          <span class="check-meta">{{ cap.id }}</span>
        </label>
      </Section>

      <ChatRagPanel
        v-if="workflowAcceptsRag"
        :global-config="globalConfig"
        v-model:selectedRag="selectedRagLocal"
      />
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, watch, h } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import ChatRagPanel from './ChatRagPanel.vue'

const props = defineProps({
  workflow: { type: Object, required: true },
  capabilities: { type: Array, default: () => [] },
  availableServers: { type: Array, default: () => [] },
  globalConfig: { type: Object, required: true },
  selectedRag: { type: Array, default: () => [] },
  collapsed: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'update:selectedRag'])

// Tiny inline section component to avoid yet another file for a label+slot.
// The RAG panel is its own component because its body is non-trivial; the
// server/capability lists are 4 lines of markup each, so they keep using
// this lightweight wrapper.
const Section = {
  props: { title: { type: String, required: true } },
  setup(p, { slots }) {
    return () => h('div', { class: 'sidebar-section' }, [
      h('h4', { class: 'section-title' }, p.title),
      h('div', { class: 'section-body' }, slots.default?.()),
    ])
  },
}

// --- Servers / Capabilities -------------------------------------------------
const enabledServers = computed({
  get: () => props.globalConfig.serversByWorkflow?.[props.workflow.id] || [],
  set: (v) => {
    if (!props.globalConfig.serversByWorkflow) props.globalConfig.serversByWorkflow = {}
    props.globalConfig.serversByWorkflow[props.workflow.id] = v
  },
})
const enabledCapabilities = computed({
  get: () => props.globalConfig.capabilitiesByWorkflow?.[props.workflow.id] || [],
  set: (v) => {
    if (!props.globalConfig.capabilitiesByWorkflow) props.globalConfig.capabilitiesByWorkflow = {}
    props.globalConfig.capabilitiesByWorkflow[props.workflow.id] = v
  },
})

const serverChoices = computed(() => {
  const wf = props.workflow || {}
  const required = new Set(wf.required_servers || [])
  const optional = new Set(wf.optional_servers || [])
  return (props.availableServers || [])
    .filter(s => required.has(s.name) || optional.has(s.name))
    .map(s => ({ ...s, required: required.has(s.name) }))
})

const capabilityChoices = computed(() => {
  const accepted = new Set(props.workflow?.accepted_capabilities || [])
  return (props.capabilities || []).filter(c => accepted.has(c.id))
})

function toggleServer(name, checked) {
  const cur = new Set(enabledServers.value)
  if (checked) cur.add(name); else cur.delete(name)
  enabledServers.value = [...cur]
}
function toggleCapability(id, checked) {
  const cur = new Set(enabledCapabilities.value)
  if (checked) cur.add(id); else cur.delete(id)
  enabledCapabilities.value = [...cur]
}

// --- RAG plumbing -----------------------------------------------------------
// We don't own RAG state; ChatRagPanel does. We just gate-mount it on the
// workflow's capability list and forward the selectedRag v-model.
const workflowAcceptsRag = computed(() =>
  (props.workflow?.accepted_capabilities || []).includes('rag')
)

const selectedRagLocal = ref([...props.selectedRag])
watch(selectedRagLocal, (v) => emit('update:selectedRag', v))
watch(() => props.selectedRag, (v) => {
  if (JSON.stringify(v) !== JSON.stringify(selectedRagLocal.value)) {
    selectedRagLocal.value = [...v]
  }
})
</script>

<style scoped>
.chat-sidebar {
  position: relative;
  width: 320px;
  flex-shrink: 0;
  height: 100%;
  background-color: #1f1f1f;
  border-left: 1px solid #3a3a3a;
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
}
.chat-sidebar.collapsed { width: 36px; }
.sidebar-header {
  /* Mirrors .chat-header on the left so the bottom border reads as one
     continuous line across the top of the screen and the collapse-toggle
     sits at the same vertical centerline as the Back button + workflow
     title in the chat header. */
  display: flex;
  align-items: center;
  padding: 0.5rem 0.85rem;
  border-bottom: 1px solid #3a3a3a;
  flex-shrink: 0;
}
.collapse-toggle {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  background: transparent;
  border: 1px solid #3a3a3a;
  color: #7a7a7a;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
}
.collapse-toggle:hover { background-color: rgba(255, 255, 255, 0.05); }
.sidebar-body {
  padding: 0.9rem 1rem 1.2rem 1rem;
  overflow-y: auto;
  flex: 1;
}
.sidebar-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: #d0d0d0;
  margin: 0 0 0.3rem 0;
}
.sidebar-desc {
  font-size: 0.82rem;
  color: #ccc;
  line-height: 1.45;
  margin: 0 0 1rem 0;
}
.sidebar-section {
  margin-top: 1.1rem;
  padding-top: 1rem;
  border-top: 1px solid #2c2c2c;
}
.section-title {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #7a7a7a;
  margin-bottom: 0.5rem;
  font-weight: 600;
}
.section-body { display: flex; flex-direction: column; gap: 0.35rem; }
.check-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #f5f5f5;
  cursor: pointer;
  padding: 0.25rem 0;
  flex-wrap: wrap;
}
.check-row input[type="checkbox"] { accent-color: #7a7a7a; }
.check-name { color: #f5f5f5; }
.check-meta { color: #888888; font-size: 0.72rem; }
</style>
