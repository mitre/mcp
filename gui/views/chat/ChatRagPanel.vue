<!--
  RAG configuration + file picker for the chat sidebar.

  Owns three things, all keyed off `globalConfig.capabilitySettings.rag`:
   - TopK / embed-model inputs (writes back through computed get/set)
   - Upload form (delegates to useRagFiles)
   - File list with checkbox selection (v-model:selectedRag bubbles up)

  The parent (ChatSidebar) decides whether this panel is mounted at all
  based on `workflow.accepted_capabilities.includes('rag')`. The panel
  itself does not gate-check; if it's mounted, it works.

  $api is *injected*, not received as a prop. Vue 3 reserves the `$`
  prefix on the component instance (`$attrs`, `$emit`, …) and a prop
  named `$api` does not survive the prop pipeline — that was the bug
  this refactor exists to fix.
-->
<template>
  <section class="rag-panel">
    <h4 class="section-title">RAG Data</h4>

    <div class="field-row">
      <label class="field-label">RAG profile</label>
      <select class="text-input" v-model="ragProfileName" @change="applyRagProfile">
        <option value="">Manual / chat fallback</option>
        <option
          v-for="profile in endpointProfiles"
          :key="profile.name"
          :value="profile.name"
        >
          {{ profile.name }}
        </option>
      </select>
      <div class="profile-actions">
        <input
          class="text-input"
          type="text"
          v-model="ragProfileDraftName"
          placeholder="Profile name"
        />
        <button class="btn primary small" type="button" @click="saveRagProfile">
          Save
        </button>
      </div>
    </div>

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

    <div class="field-row">
      <label class="field-label">API base</label>
      <input
        class="text-input"
        type="text"
        v-model="ragSettings.embed_api_base"
        placeholder="Blank = chat endpoint"
      />
    </div>

    <div class="field-row">
      <label class="field-label">API key</label>
      <input
        class="text-input"
        type="password"
        v-model="ragSettings.embed_api_key"
        placeholder="Use chat key"
      />
    </div>

    <div class="field-row">
      <label class="checkbox">
        <input type="checkbox" v-model="ragSslVerify" />
        Verify TLS certificates
      </label>
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
  </section>
</template>

<script setup>
import { ref, computed, inject, onMounted, watch } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { useRagFiles, formatBytes, formatDate } from './composables/useRagFiles.js'

const props = defineProps({
  // Shared per-workflow config object (the chat orchestrator persists this).
  // We mutate `capabilitySettings.rag.{topk,embed_model}` in place; the
  // parent does not need to react to those edits separately.
  globalConfig: { type: Object, required: true },
  // Currently checked filenames. Two-way bound via update:selectedRag so the
  // chat orchestrator stays the single source of truth for which files
  // attach to the next prompt.
  selectedRag: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:selectedRag'])

const $api = inject('$api')

// `capabilitySettings.rag` is the durable home for TopK / embed model.
// Lazily seed the slot so the v-model bindings can write into it without
// a no-op render on first mount.
const ragSettings = computed(() => {
  const cfg = props.globalConfig
  if (!cfg.capabilitySettings) cfg.capabilitySettings = {}
  if (!cfg.capabilitySettings.rag) cfg.capabilitySettings.rag = {}
  return cfg.capabilitySettings.rag
})
const ragProfileDraftName = ref('')
const endpointProfiles = computed(() => {
  if (!Array.isArray(props.globalConfig.endpointProfiles)) props.globalConfig.endpointProfiles = []
  return props.globalConfig.endpointProfiles
})
const ragProfileName = computed({
  get: () => ragSettings.value.profile || '',
  set: (value) => {
    ragSettings.value.profile = value || ''
    if (value) ragProfileDraftName.value = value
  },
})
const ragSslVerify = computed({
  get: () => ragSettings.value.ssl_verify ?? props.globalConfig.sslVerify ?? true,
  set: (value) => {
    ragSettings.value.ssl_verify = value
  },
})

function profileName(value) {
  return String(value || '').trim()
}

function applyProfileToRag(profile) {
  if (!profile) return
  ragSettings.value.embed_model = profile.modelName || profile.model || ''
  ragSettings.value.embed_api_base = profile.apiBase || profile.api_base || ''
  ragSettings.value.embed_api_key = profile.apiKey || profile.api_key || ''
  ragSettings.value.ssl_verify = profile.sslVerify ?? profile.ssl_verify ?? props.globalConfig.sslVerify ?? true
  ragSettings.value.temperature = profile.temperature
  ragSettings.value.max_tool_calls = profile.maxToolCalls ?? profile.max_tool_calls
  ragSettings.value.max_tokens = profile.maxTokens ?? profile.max_tokens
  if (profile.topk != null) ragSettings.value.topk = Number(profile.topk)
  ragProfileDraftName.value = profile.name || ''
}

function applyRagProfile() {
  const profile = endpointProfiles.value.find(p => p.name === ragProfileName.value)
  if (profile) applyProfileToRag(profile)
}

function saveRagProfile() {
  const name = profileName(ragProfileDraftName.value || ragProfileName.value)
  if (!name) return
  const profile = {
    name,
    modelName: ragSettings.value.embed_model || props.globalConfig.modelName || '',
    temperature: ragSettings.value.temperature ?? props.globalConfig.temperature,
    apiBase: ragSettings.value.embed_api_base || props.globalConfig.apiBase || '',
    apiKey: ragSettings.value.embed_api_key || props.globalConfig.apiKey || '',
    sslVerify: ragSslVerify.value,
    maxToolCalls: ragSettings.value.max_tool_calls ?? props.globalConfig.maxToolCalls,
    maxTokens: ragSettings.value.max_tokens ?? props.globalConfig.maxTokens,
    topk: ragSettings.value.topk,
  }
  props.globalConfig.endpointProfiles = [
    ...endpointProfiles.value.filter(existing => existing.name !== name),
    profile,
  ].sort((a, b) => a.name.localeCompare(b.name))
  ragProfileName.value = name
}

const {
  ragFiles,
  selectedFile,
  isUploading,
  uploadMessage,
  uploadError,
  onFileSelected,
  fetchRagFiles,
  uploadRag,
} = useRagFiles($api)

// Mirror the parent's selectedRag in a local ref. We watch both directions
// so the orchestrator can clear / preset selection (e.g. on workflow
// switch) while the user's checkbox edits still bubble up.
const selectedRagLocal = ref([...props.selectedRag])
watch(selectedRagLocal, (v) => emit('update:selectedRag', v))
watch(() => props.selectedRag, (v) => {
  if (JSON.stringify(v) !== JSON.stringify(selectedRagLocal.value)) {
    selectedRagLocal.value = [...v]
  }
})

// Drop selections that no longer exist on disk after each list refresh.
// Keeps the chat payload consistent if a file disappears between mounts.
watch(ragFiles, (files) => {
  const available = new Set(files.map((f) => f.filename))
  const pruned = selectedRagLocal.value.filter((name) => available.has(name))
  if (pruned.length !== selectedRagLocal.value.length) {
    selectedRagLocal.value = pruned
  }
})

onMounted(fetchRagFiles)
</script>

<style scoped>
/* Visual style is owned by ChatSidebar.vue's section conventions. We only
   restate the rules this panel uses so the component renders correctly
   even if it's ever moved out of the sidebar. */
.rag-panel {
  margin-top: 1.1rem;
  padding-top: 1rem;
  border-top: 1px solid #2c2c2c;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.section-title {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #7a7a7a;
  margin-bottom: 0.5rem;
  font-weight: 600;
}
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
  text-align: left;
  align-self: flex-start;
  display: block;
  width: 100%;
}
.num-input, .text-input {
  background-color: #2a2a2a;
  color: #f5f5f5;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  padding: 0.4rem 0.55rem;
  font-size: 0.85rem;
  width: 100%;
  min-width: 0;
}
.profile-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.35rem;
  align-items: stretch;
}
.file-picker { margin-top: 0.6rem; }
.file-label { display: block; margin-bottom: 0.5rem; }
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
  text-align: left;
  margin-bottom: 0.3rem;
}
.muted { color: #6b6585; font-size: 0.8rem; font-style: italic; }
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
.file-row .check-name { font-family: ui-monospace, Menlo, monospace; font-size: 0.78rem; }
</style>
