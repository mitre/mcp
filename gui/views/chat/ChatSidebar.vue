<!--
  Collapsible left rail with workflow-scoped configuration: enabled MCP
  servers, capabilities, and (when this workflow accepts the rag capability)
  the RAG file picker + upload form. All state is read/written through
  globalConfig keyed by workflow.id, the same contract the legacy view used.
-->
<template>
  <aside class="chat-sidebar" :class="{ collapsed }">
    <button class="collapse-toggle" @click="$emit('toggle')" type="button"
            :title="collapsed ? 'Expand panel' : 'Collapse panel'">
      <font-awesome-icon :icon="['fas', collapsed ? 'angle-left' : 'angle-right']" />
    </button>

    <div v-if="!collapsed" class="sidebar-body">
      <button class="back-button" @click="$emit('back')" type="button">
        <font-awesome-icon :icon="['fas', 'angle-left']" />
        <span>Back</span>
      </button>

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

      <Section title="RAG Data" v-if="workflowAcceptsRag">
        <div class="field-row">
          <label class="field-label">TopK</label>
          <input
            class="num-input"
            type="number"
            min="1"
            max="30"
            step="1"
            v-model.number="ragSettings.topk"
          />
        </div>
        <div class="field-row">
          <label class="field-label">Embed model</label>
          <input
            class="text-input"
            type="text"
            v-model="ragSettings.embed_model"
            placeholder="openai/text-embedding-3-small"
          />
        </div>

        <div class="file-picker">
          <label class="file-label">
            <input
              type="file"
              accept=".json,application/json"
              @change="onFileSelected"
              :disabled="isUploading"
            />
            <span class="file-cta">
              <font-awesome-icon :icon="['fas', 'plus']" />
              <span>{{ selectedFile ? selectedFile.name : 'Choose JSON file…' }}</span>
            </span>
          </label>
          <div class="file-actions">
            <button
              class="btn primary small"
              @click="uploadRag"
              :disabled="!selectedFile || isUploading"
              type="button"
            >
              {{ isUploading ? 'Uploading…' : 'Upload' }}
            </button>
            <button
              class="btn ghost small"
              @click="fetchRagFiles"
              :disabled="isUploading"
              type="button"
            >
              Refresh
            </button>
          </div>
          <p v-if="uploadMessage" class="msg success">{{ uploadMessage }}</p>
          <p v-if="uploadError" class="msg error">{{ uploadError }}</p>
        </div>

        <div class="file-list">
          <strong class="file-list-title">Available files</strong>
          <p v-if="ragFiles.length === 0" class="muted">No files uploaded.</p>
          <label
            v-for="f in ragFiles"
            :key="f.filename"
            class="check-row file-row"
          >
            <input
              type="checkbox"
              :value="f.filename"
              v-model="selectedRagLocal"
              :disabled="isUploading"
            />
            <span class="check-name">{{ f.filename }}</span>
            <span class="check-meta">
              {{ formatBytes(f.size) }} · {{ formatDate(f.modified) }}
            </span>
          </label>
        </div>
      </Section>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, watch, h } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'

const props = defineProps({
  workflow: { type: Object, required: true },
  capabilities: { type: Array, default: () => [] },
  availableServers: { type: Array, default: () => [] },
  globalConfig: { type: Object, required: true },
  $api: { type: Object, required: true },
  selectedRag: { type: Array, default: () => [] },
  collapsed: { type: Boolean, default: false },
})
const emit = defineEmits(['back', 'toggle', 'update:selectedRag'])

// Tiny inline section component to avoid yet another file for a label+slot.
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

// --- RAG --------------------------------------------------------------------
const workflowAcceptsRag = computed(() =>
  (props.workflow?.accepted_capabilities || []).includes('rag')
)
const ragSettings = computed(() => {
  if (!props.globalConfig.capabilitySettings) props.globalConfig.capabilitySettings = {}
  if (!props.globalConfig.capabilitySettings.rag) props.globalConfig.capabilitySettings.rag = {}
  return props.globalConfig.capabilitySettings.rag
})

const selectedFile = ref(null)
const isUploading = ref(false)
const ragFiles = ref([])
const uploadMessage = ref('')
const uploadError = ref('')

// Mirror parent's selectedRag through v-model so the orchestrator stays the
// single source of truth for "which files are attached to the next prompt."
const selectedRagLocal = ref([...props.selectedRag])
watch(selectedRagLocal, (v) => emit('update:selectedRag', v))
watch(() => props.selectedRag, (v) => {
  if (JSON.stringify(v) !== JSON.stringify(selectedRagLocal.value)) {
    selectedRagLocal.value = [...v]
  }
})

function onFileSelected(e) {
  uploadMessage.value = ''
  uploadError.value = ''
  const file = e.target.files?.[0]
  if (!file) { selectedFile.value = null; return }
  const isJson = file.type === 'application/json' || file.name.toLowerCase().endsWith('.json')
  if (!isJson) {
    selectedFile.value = null
    uploadError.value = 'Please select a .json file.'
    return
  }
  selectedFile.value = file
}

async function uploadRag() {
  if (!selectedFile.value) return
  isUploading.value = true
  uploadMessage.value = ''
  uploadError.value = ''
  try {
    const fd = new FormData()
    fd.append('file', selectedFile.value)
    const res = await props.$api.post('/plugin/mcp/rag/upload', fd)
    uploadMessage.value = `Uploaded ${res.data.filename} (${formatBytes(res.data.size)})`
    selectedFile.value = null
    await fetchRagFiles()
  } catch (err) {
    uploadError.value = err?.response?.data?.error || 'Upload failed.'
  } finally {
    isUploading.value = false
  }
}

async function fetchRagFiles() {
  try {
    const res = await props.$api.get('/plugin/mcp/rag/list')
    ragFiles.value = res.data.files || []
    // Drop selections that no longer exist on disk.
    const available = new Set(ragFiles.value.map(f => f.filename))
    selectedRagLocal.value = selectedRagLocal.value.filter(name => available.has(name))
  } catch (err) {
    uploadError.value = err?.response?.data?.error || 'Failed to fetch RAG files.'
  }
}

function formatBytes(bytes) {
  if (bytes === 0 || bytes == null) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}
function formatDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

onMounted(() => {
  if (workflowAcceptsRag.value) fetchRagFiles()
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
.collapse-toggle {
  position: absolute;
  top: 12px;
  left: 8px;
  width: 24px;
  height: 24px;
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
.back-button {
  background: transparent;
  border: none;
  color: #888888;
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0.2rem 0 0.2rem 1.8rem;
  margin-bottom: 0.6rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.back-button:hover { color: #d0d0d0; }
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
.field-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.6rem;
}
.field-label {
  font-size: 0.72rem;
  color: #888888;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.num-input, .text-input {
  background-color: #2a2a2a;
  color: #f5f5f5;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.4rem 0.55rem;
  font-size: 0.85rem;
}
.file-picker { margin-top: 0.6rem; }
.file-label {
  display: block;
  margin-bottom: 0.5rem;
}
.file-label input[type="file"] { display: none; }
.file-cta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background-color: #2a2a2a;
  border: 1px dashed #3a3a3a;
  border-radius: 4px;
  padding: 0.5rem 0.7rem;
  color: #d0d0d0;
  font-size: 0.82rem;
  cursor: pointer;
}
.file-cta:hover { background-color: #2c2c2c; }
.file-actions { display: flex; gap: 0.4rem; }
.btn {
  border-radius: 4px;
  border: 1px solid #3a3a3a;
  cursor: pointer;
  font-size: 0.82rem;
  padding: 0.35rem 0.7rem;
}
.btn.small { padding: 0.3rem 0.6rem; font-size: 0.78rem; }
.btn.primary { background-color: #7a7a7a; color: #fff; border-color: #7a7a7a; }
.btn.primary:hover:not(:disabled) { background-color: #c08fff; }
.btn.ghost { background-color: transparent; color: #d0d0d0; }
.btn.ghost:hover:not(:disabled) { background-color: rgba(255, 255, 255, 0.05); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.msg { font-size: 0.78rem; margin: 0.5rem 0 0 0; }
.msg.success { color: #8be78b; }
.msg.error   { color: #ff8b8b; }
.file-list { margin-top: 0.7rem; max-height: 200px; overflow-y: auto; }
.file-list-title {
  display: block;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #888888;
  margin-bottom: 0.3rem;
}
.muted { color: #6b6585; font-size: 0.8rem; font-style: italic; }
.file-row .check-name { font-family: ui-monospace, Menlo, monospace; font-size: 0.78rem; }
</style>
