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
        <font-awesome-icon :icon="collapseIcon" />
      </button>
    </header>

    <div v-if="!collapsed" class="sidebar-body">
      <Section title="LLM Endpoint" v-if="isPlanExecute">
        <button class="picker-toggle model-toggle" type="button" @click="modelConfigOpen = !modelConfigOpen">
          <font-awesome-icon :icon="modelToggleIcon" />
          <span>Model</span>
          <span class="check-meta">{{ modelConfigSummary }}</span>
        </button>

        <div v-if="modelConfigOpen" class="model-config-panel">
          <label class="field-label" for="plan-endpoint-profile">Endpoint profile</label>
          <select
            id="plan-endpoint-profile"
            class="compact-select"
            v-model="selectedEndpointProfileName"
            @change="applySelectedEndpointProfile"
          >
            <option value="">Manual settings</option>
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
              class="compact-input"
              type="text"
              v-model="endpointProfileDraftName"
              placeholder="Profile name"
            />
            <button class="mini-button primary" type="button" @click="saveGlobalEndpointProfile">
              Save
            </button>
            <button
              class="mini-button"
              type="button"
              @click="deleteSelectedEndpointProfile"
              :disabled="!selectedEndpointProfileName"
            >
              Delete
            </button>
          </div>

          <label class="field-label" for="plan-model-name">Model</label>
            <input
              id="plan-model-name"
              class="compact-input"
              type="text"
              v-model="globalConfig.modelName"
              placeholder="provider/model-name"
            />

          <label class="field-label" for="plan-api-base">API base</label>
          <input
            id="plan-api-base"
              class="compact-input"
              type="text"
              v-model="globalConfig.apiBase"
              placeholder="https://api.example.com/v1"
            />

          <label class="field-label" for="plan-api-key">API key</label>
          <input
            id="plan-api-key"
            class="compact-input"
            type="password"
            v-model="globalConfig.apiKey"
            placeholder="Use server default or enter a key"
          />

          <label class="check-row tls-check">
            <input type="checkbox" v-model="globalConfig.sslVerify" />
            <span class="check-name">Verify TLS certificates</span>
          </label>

          <div class="model-grid">
            <label>
              <span class="field-label">Temperature</span>
              <input
                class="compact-input"
                type="number"
                v-model.number="globalConfig.temperature"
                step="0.1"
                min="0"
                max="2"
              />
            </label>
            <label>
              <span class="field-label">Tool calls</span>
              <input
                class="compact-input"
                type="number"
                v-model.number="globalConfig.maxToolCalls"
                min="1"
                step="1"
              />
            </label>
            <label>
              <span class="field-label">Max tokens</span>
              <input
                class="compact-input"
                type="number"
                v-model.number="globalConfig.maxTokens"
                min="1000"
                step="1000"
              />
            </label>
          </div>
        </div>
      </Section>

      <Section title="MCP Tool Servers" v-if="serverChoices.length">
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

      <Section title="Capabilities" v-if="!isPlanExecute && capabilityChoices.length">
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
        v-if="workflowAcceptsRag && !isPlanExecute"
        :global-config="globalConfig"
        v-model:selectedRag="selectedRagLocal"
      />

      <Section title="CTI / Range" v-if="isPlanExecute">
        <button class="picker-toggle" type="button" @click="openStixModal">
          <font-awesome-icon :icon="folderOpenIcon" />
          <span>STIX</span>
          <span class="check-meta">{{ selectedPlanStix.length }} selected</span>
        </button>

        <div v-if="selectedStixFiles.length" class="selected-list">
          <div v-for="file in selectedStixFiles" :key="file.name" class="selected-row">
            <span class="selected-copy">
              <span class="check-name truncate">{{ file.name }}</span>
              <span class="check-meta">{{ stixMeta(file) }}</span>
            </span>
            <button
              class="remove-chip"
              type="button"
              @click="togglePlanStix(file.name, false)"
              :title="`Remove ${file.name}`"
            >
              <font-awesome-icon :icon="timesIcon" />
            </button>
          </div>
        </div>
        <div v-else class="empty-row">No STIX selected. Selecting STIX automatically enables CTI RAG.</div>

        <div v-if="selectedPlanStix.length" class="cti-rag-panel">
          <div class="field-stack tight">
            <label class="field-label" for="plan-cti-rag-profile">CTI RAG profile</label>
            <select
              id="plan-cti-rag-profile"
              class="compact-select"
              v-model="ctiRagProfile"
              @change="applyCtiRagProfile"
            >
              <option value="">Manual / chat fallback</option>
              <option
                v-for="profile in endpointProfiles"
                :key="profile.name"
                :value="profile.name"
              >
                {{ profile.name }}
              </option>
            </select>

            <label class="field-label" for="plan-cti-rag-model">CTI RAG model</label>
            <input
              id="plan-cti-rag-model"
              class="compact-input"
              type="text"
              v-model="ctiRagModel"
              placeholder="Blank = configured RAG default"
            />
            <div class="helper-row">
              Blank model uses the RAG default. Blank endpoint and key use the chat endpoint.
            </div>

            <label class="field-label" for="plan-cti-rag-api-base">CTI RAG API base</label>
            <input
              id="plan-cti-rag-api-base"
              class="compact-input"
              type="text"
              v-model="ctiRagApiBase"
              placeholder="Blank = chat endpoint"
            />

            <label class="field-label" for="plan-cti-rag-api-key">CTI RAG API key</label>
            <input
              id="plan-cti-rag-api-key"
              class="compact-input"
              type="password"
              v-model="ctiRagApiKey"
              placeholder="Use chat key"
            />

            <label class="check-row tls-check">
              <input type="checkbox" v-model="ctiRagSslVerify" />
              <span class="check-name">Verify CTI RAG TLS certificates</span>
            </label>

            <div class="model-grid">
              <label>
                <span class="field-label">TopK</span>
                <input
                  class="compact-input"
                  type="number"
                  v-model.number="ctiRagTopk"
                  min="1"
                  max="30"
                  step="1"
                />
              </label>
              <label>
                <span class="field-label">Temperature</span>
                <input
                  class="compact-input"
                  type="number"
                  v-model.number="ctiRagTemperature"
                  step="0.1"
                  min="0"
                  max="2"
                  :placeholder="String(globalConfig.temperature ?? '')"
                />
              </label>
              <label>
                <span class="field-label">Tool calls</span>
                <input
                  class="compact-input"
                  type="number"
                  v-model.number="ctiRagMaxToolCalls"
                  min="1"
                  step="1"
                  :placeholder="String(globalConfig.maxToolCalls ?? '')"
                />
              </label>
              <label>
                <span class="field-label">Max tokens</span>
                <input
                  class="compact-input"
                  type="number"
                  v-model.number="ctiRagMaxTokens"
                  min="1000"
                  step="1000"
                  :placeholder="String(globalConfig.maxTokens ?? '')"
                />
              </label>
            </div>

            <div class="profile-actions">
              <input
                class="compact-input"
                type="text"
                v-model="ctiRagProfileDraftName"
                placeholder="Profile name"
              />
              <button class="mini-button primary" type="button" @click="saveCtiRagProfile">
                Save
              </button>
            </div>
          </div>
        </div>
      </Section>

      <Section title="Build Range" v-if="isPlanExecute">

        <label class="check-row">
          <input type="checkbox" v-model="buildRange" />
          <span class="check-name">Build range</span>
        </label>

        <div v-if="buildRange" class="field-stack">
          <div class="field-label">Hypervisors</div>
          <label
            v-for="provider in rangeProviders"
            :key="providerName(provider)"
            class="check-row provider-row"
            :class="{ selected: selectedRangeProviders.includes(providerName(provider)) }"
            :title="providerTitle(provider)"
          >
            <input
              type="checkbox"
              :checked="selectedRangeProviders.includes(providerName(provider))"
              @change="toggleRangeProvider(providerName(provider), $event.target.checked)"
            />
            <span class="selected-copy">
              <span class="check-name">{{ providerName(provider) }}</span>
              <span class="check-meta">{{ providerMeta(provider) }}</span>
            </span>
          </label>
          <div v-if="!rangeProviders.length" class="empty-row">No Range hypervisors loaded</div>

          <div class="capability-line">
            <span>{{ rangeImages.length }} images</span>
            <span>{{ featureCount }} features</span>
            <span v-if="microvmStatus">{{ microvmStatus }}</span>
          </div>

          <div class="identity-grid">
            <label><input type="checkbox" v-model="identityDomain" /> Domain</label>
            <label><input type="checkbox" v-model="identityDomainUsers" /> Domain users</label>
            <label><input type="checkbox" v-model="identityLocalUsers" /> Local users</label>
          </div>

          <div class="field-stack tight">
            <label class="field-label" for="plan-agent-mode">Agent</label>
            <select id="plan-agent-mode" class="compact-select" v-model="agentMode">
              <option value="sandcat">Sandcat</option>
              <option value="custom">Custom</option>
              <option value="cti">CTI decides</option>
            </select>
            <label class="check-row compact">
              <input type="checkbox" v-model="agentUseCtiEntry" />
              <span class="check-name">CTI entry host</span>
            </label>
          </div>

          <div v-if="rangeError" class="error-row">{{ rangeError }}</div>
        </div>
      </Section>
    </div>
  </aside>

  <Teleport to="body">
    <div v-if="showStixModal" class="modal-scrim" @click.self="closeStixModal">
      <div class="stix-modal" role="dialog" aria-modal="true" aria-labelledby="stix-modal-title">
        <header class="modal-header">
          <div>
            <h3 id="stix-modal-title">Generated STIX Objects</h3>
            <p>{{ selectedPlanStix.length }} selected for Plan and Execute</p>
          </div>
          <button class="modal-close" type="button" @click="closeStixModal" title="Close">
            <font-awesome-icon :icon="timesIcon" />
          </button>
        </header>

        <div class="modal-toolbar">
          <span>{{ stixFiles.length }} files</span>
          <div class="toolbar-actions">
            <button type="button" @click="selectAllStix">All</button>
            <button type="button" @click="clearPlanStix">Clear</button>
          </div>
        </div>

        <div class="stix-table-wrap">
          <table class="stix-table">
            <thead>
              <tr>
                <th class="select-col">Select</th>
                <th>File</th>
                <th>Model</th>
                <th>Provider</th>
                <th class="right">Size</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="file in stixFiles"
                :key="file.name"
                :class="{ selected: selectedPlanStix.includes(file.name) }"
                @click="togglePlanStix(file.name, !selectedPlanStix.includes(file.name))"
              >
                <td class="select-col">
                  <input
                    type="checkbox"
                    :checked="selectedPlanStix.includes(file.name)"
                    @click.stop
                    @change="togglePlanStix(file.name, $event.target.checked)"
                  />
                </td>
                <td class="file-cell">{{ file.name }}</td>
                <td>{{ file.model || '-' }}</td>
                <td>{{ file.provider || '-' }}</td>
                <td class="right">{{ formatKb(file.size) || '-' }}</td>
              </tr>
              <tr v-if="!stixFiles.length">
                <td colspan="5" class="empty-cell">No STIX generated yet</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, h, inject, onMounted } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import {
  faAngleDown,
  faAngleLeft,
  faAngleRight,
  faFolderOpen,
  faTimes,
} from '@fortawesome/free-solid-svg-icons'
import ChatRagPanel from './ChatRagPanel.vue'

const props = defineProps({
  workflow: { type: Object, required: true },
  capabilities: { type: Array, default: () => [] },
  availableServers: { type: Array, default: () => [] },
  globalConfig: { type: Object, required: true },
  selectedRag: { type: Array, default: () => [] },
  workflowContext: { type: Object, default: () => ({}) },
  collapsed: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'update:selectedRag', 'update:workflowContext'])
const $api = inject('$api', null)

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

// --- Plan and Execute CTI / Range context ----------------------------------
const isPlanExecute = computed(() => props.workflow?.id === 'plan_execute')
const modelConfigOpen = ref(false)
const showStixModal = ref(false)
const stixFiles = ref([])
const selectedPlanStix = ref([])
const buildRange = ref(false)
const rangeProviders = ref([])
const selectedRangeProviders = ref([])
const rangeImagesByProvider = ref({})
const rangeFeatures = ref({ default: [], custom: [] })
const microvmSubstrate = ref({})
const rangeError = ref('')
const identityDomain = ref(true)
const identityDomainUsers = ref(true)
const identityLocalUsers = ref(true)
const agentMode = ref('sandcat')
const agentUseCtiEntry = ref(true)

function ensureRagSettings() {
  if (!props.globalConfig.capabilitySettings) props.globalConfig.capabilitySettings = {}
  if (!props.globalConfig.capabilitySettings.rag) props.globalConfig.capabilitySettings.rag = {}
  return props.globalConfig.capabilitySettings.rag
}

const planRagSettings = computed(() => ensureRagSettings())
const endpointProfileDraftName = ref(props.globalConfig.selectedEndpointProfile || '')
const ctiRagProfileDraftName = ref('')
const endpointProfiles = computed(() => {
  if (!Array.isArray(props.globalConfig.endpointProfiles)) props.globalConfig.endpointProfiles = []
  return props.globalConfig.endpointProfiles
})
const selectedEndpointProfileName = computed({
  get: () => props.globalConfig.selectedEndpointProfile || '',
  set: (value) => {
    props.globalConfig.selectedEndpointProfile = value || ''
    if (value) endpointProfileDraftName.value = value
  },
})
const ctiRagProfile = computed({
  get: () => planRagSettings.value.plan_profile || '',
  set: (value) => {
    planRagSettings.value.plan_profile = value || ''
    if (value) ctiRagProfileDraftName.value = value
  },
})
const ctiRagModel = computed({
  get: () => planRagSettings.value.plan_embed_model || '',
  set: (value) => {
    planRagSettings.value.plan_embed_model = value
  },
})
const ctiRagApiBase = computed({
  get: () => planRagSettings.value.plan_api_base || '',
  set: (value) => {
    planRagSettings.value.plan_api_base = value
  },
})
const ctiRagApiKey = computed({
  get: () => planRagSettings.value.plan_api_key || '',
  set: (value) => {
    planRagSettings.value.plan_api_key = value
  },
})
const ctiRagSslVerify = computed({
  get: () => planRagSettings.value.plan_ssl_verify ?? props.globalConfig.sslVerify ?? true,
  set: (value) => {
    planRagSettings.value.plan_ssl_verify = value
  },
})
const ctiRagTopk = computed({
  get: () => planRagSettings.value.plan_topk ?? planRagSettings.value.topk ?? 5,
  set: (value) => {
    planRagSettings.value.plan_topk = value
  },
})
const ctiRagTemperature = computed({
  get: () => planRagSettings.value.plan_temperature ?? '',
  set: (value) => {
    planRagSettings.value.plan_temperature = value
  },
})
const ctiRagMaxToolCalls = computed({
  get: () => planRagSettings.value.plan_max_tool_calls ?? '',
  set: (value) => {
    planRagSettings.value.plan_max_tool_calls = value
  },
})
const ctiRagMaxTokens = computed({
  get: () => planRagSettings.value.plan_max_tokens ?? '',
  set: (value) => {
    planRagSettings.value.plan_max_tokens = value
  },
})
const modelConfigSummary = computed(() =>
  props.globalConfig?.modelName || 'server default'
)
const collapseIcon = computed(() => props.collapsed ? faAngleLeft : faAngleRight)
const modelToggleIcon = computed(() => modelConfigOpen.value ? faAngleDown : faAngleRight)
const folderOpenIcon = faFolderOpen
const timesIcon = faTimes

const featureCount = computed(() => {
  const f = rangeFeatures.value || {}
  return (Array.isArray(f.default) ? f.default.length : 0)
    + (Array.isArray(f.custom) ? f.custom.length : 0)
    + (Array.isArray(f.features) ? f.features.length : 0)
})

const selectedStixFiles = computed(() =>
  selectedPlanStix.value.map(name =>
    stixFiles.value.find(file => file.name === name) || { name }
  )
)

const rangeProvider = computed(() => selectedRangeProviders.value[0] || '')

const rangeImages = computed(() =>
  selectedRangeProviders.value.flatMap(provider => rangeImagesByProvider.value[provider] || [])
)

const microvmStatus = computed(() => {
  const s = microvmSubstrate.value || {}
  return s.status || s.state || ''
})

async function apiGet(url) {
  if ($api?.get) {
    const res = await $api.get(url)
    return res.data || {}
  }
  const res = await fetch(url)
  if (!res.ok) throw new Error(`GET ${url} returned ${res.status}`)
  return await res.json()
}

function formatKb(size) {
  const n = Number(size || 0)
  return n ? `${(n / 1024).toFixed(1)} KB` : ''
}

function stixMeta(file) {
  const bits = [file?.model, file?.provider, formatKb(file?.size)].filter(Boolean)
  return bits.join(' / ')
}

function providerName(provider) {
  return provider?.name || provider?.provider || ''
}

function providerMeta(provider) {
  const images = Number(provider?.image_count || 0)
  const profiles = Number(provider?.profile_count || 0)
  return `${images} images / ${profiles} profiles`
}

function providerTitle(provider) {
  const profiles = Array.isArray(provider?.profiles) ? provider.profiles.join(', ') : ''
  return profiles ? `${providerName(provider)} profiles: ${profiles}` : providerName(provider)
}

function trimmedProfileName(value) {
  return String(value || '').trim()
}

function upsertEndpointProfile(profile) {
  const name = trimmedProfileName(profile?.name)
  if (!name) return
  const next = [
    ...endpointProfiles.value.filter(existing => existing.name !== name),
    { ...profile, name },
  ].sort((a, b) => a.name.localeCompare(b.name))
  props.globalConfig.endpointProfiles = next
}

function currentGlobalEndpointProfile(name) {
  return {
    name,
    modelName: props.globalConfig.modelName || '',
    temperature: props.globalConfig.temperature,
    apiBase: props.globalConfig.apiBase || '',
    apiKey: props.globalConfig.apiKey || '',
    sslVerify: props.globalConfig.sslVerify ?? true,
    maxToolCalls: props.globalConfig.maxToolCalls,
    maxTokens: props.globalConfig.maxTokens,
  }
}

function currentCtiRagProfile(name) {
  return {
    name,
    modelName: ctiRagModel.value || props.globalConfig.modelName || '',
    temperature: ctiRagTemperature.value !== ''
      ? ctiRagTemperature.value
      : props.globalConfig.temperature,
    apiBase: ctiRagApiBase.value || props.globalConfig.apiBase || '',
    apiKey: ctiRagApiKey.value || props.globalConfig.apiKey || '',
    sslVerify: ctiRagSslVerify.value,
    maxToolCalls: ctiRagMaxToolCalls.value !== ''
      ? ctiRagMaxToolCalls.value
      : props.globalConfig.maxToolCalls,
    maxTokens: ctiRagMaxTokens.value !== ''
      ? ctiRagMaxTokens.value
      : props.globalConfig.maxTokens,
    topk: ctiRagTopk.value,
  }
}

function applyProfileToGlobal(profile) {
  if (!profile) return
  props.globalConfig.modelName = profile.modelName || profile.model || ''
  props.globalConfig.temperature = profile.temperature
  props.globalConfig.apiBase = profile.apiBase || profile.api_base || ''
  props.globalConfig.apiKey = profile.apiKey || profile.api_key || ''
  props.globalConfig.sslVerify = profile.sslVerify ?? profile.ssl_verify ?? true
  props.globalConfig.maxToolCalls = profile.maxToolCalls ?? profile.max_tool_calls
  props.globalConfig.maxTokens = profile.maxTokens ?? profile.max_tokens
  endpointProfileDraftName.value = profile.name || ''
}

function applyProfileToCtiRag(profile) {
  if (!profile) return
  ctiRagModel.value = profile.modelName || profile.model || ''
  ctiRagApiBase.value = profile.apiBase || profile.api_base || ''
  ctiRagApiKey.value = profile.apiKey || profile.api_key || ''
  ctiRagSslVerify.value = profile.sslVerify ?? profile.ssl_verify ?? props.globalConfig.sslVerify ?? true
  ctiRagTemperature.value = profile.temperature ?? ''
  ctiRagMaxToolCalls.value = profile.maxToolCalls ?? profile.max_tool_calls ?? ''
  ctiRagMaxTokens.value = profile.maxTokens ?? profile.max_tokens ?? ''
  if (profile.topk != null) ctiRagTopk.value = Number(profile.topk)
  ctiRagProfileDraftName.value = profile.name || ''
}

function applySelectedEndpointProfile() {
  const profile = endpointProfiles.value.find(p => p.name === selectedEndpointProfileName.value)
  if (profile) applyProfileToGlobal(profile)
}

function applyCtiRagProfile() {
  const profile = endpointProfiles.value.find(p => p.name === ctiRagProfile.value)
  if (profile) applyProfileToCtiRag(profile)
}

function saveGlobalEndpointProfile() {
  const name = trimmedProfileName(endpointProfileDraftName.value || selectedEndpointProfileName.value)
  if (!name) return
  upsertEndpointProfile(currentGlobalEndpointProfile(name))
  selectedEndpointProfileName.value = name
}

function saveCtiRagProfile() {
  const name = trimmedProfileName(ctiRagProfileDraftName.value || ctiRagProfile.value)
  if (!name) return
  upsertEndpointProfile(currentCtiRagProfile(name))
  ctiRagProfile.value = name
}

function deleteSelectedEndpointProfile() {
  const name = selectedEndpointProfileName.value
  if (!name) return
  props.globalConfig.endpointProfiles = endpointProfiles.value.filter(p => p.name !== name)
  selectedEndpointProfileName.value = ''
  endpointProfileDraftName.value = ''
  if (ctiRagProfile.value === name) ctiRagProfile.value = ''
}

function openStixModal() {
  showStixModal.value = true
  loadPlanStixFiles()
}

function closeStixModal() {
  showStixModal.value = false
}

function selectAllStix() {
  selectedPlanStix.value = stixFiles.value.map(file => file.name)
}

function clearPlanStix() {
  selectedPlanStix.value = []
}

function togglePlanStix(name, checked) {
  const cur = new Set(selectedPlanStix.value)
  if (checked) cur.add(name); else cur.delete(name)
  selectedPlanStix.value = [...cur]
}

function toggleRangeProvider(name, checked) {
  if (!name) return
  const cur = new Set(selectedRangeProviders.value)
  if (checked) cur.add(name); else cur.delete(name)
  selectedRangeProviders.value = [...cur]
  if (checked) loadRangeImagesForProvider(name)
}

async function loadPlanStixFiles() {
  try {
    const data = await apiGet('/plugin/mcp/stix/list')
    stixFiles.value = (data.files || [])
      .filter(f => (f.filename || '').endsWith('.json'))
      .map(f => ({
        name: f.filename,
        size: f.size,
        model: f.model,
        provider: f.provider,
      }))
  } catch (e) {
    stixFiles.value = []
  }
}

async function loadRangeProviders() {
  try {
    rangeError.value = ''
    const data = await apiGet('/plugin/range/onprem/providers')
    rangeProviders.value = Array.isArray(data.providers) ? data.providers : []
    if (!selectedRangeProviders.value.length && rangeProviders.value.length) {
      const withImages = rangeProviders.value.find(p => Number(p.image_count || 0) > 0)
      const chosen = withImages || rangeProviders.value[0]
      const chosenName = providerName(chosen)
      selectedRangeProviders.value = chosenName ? [chosenName] : []
    }
  } catch (e) {
    rangeProviders.value = []
    selectedRangeProviders.value = []
    rangeError.value = 'Range unavailable'
  }
}

async function loadRangeImagesForProvider(provider) {
  if (!provider) return
  try {
    const data = await apiGet(
      `/plugin/range/onprem/images?provider=${encodeURIComponent(provider)}`
    )
    rangeImagesByProvider.value = {
      ...rangeImagesByProvider.value,
      [provider]: Array.isArray(data.images) ? data.images : [],
    }
  } catch (e) {
    rangeImagesByProvider.value = { ...rangeImagesByProvider.value, [provider]: [] }
  }
}

async function loadRangeImages() {
  if (!selectedRangeProviders.value.length) {
    rangeImagesByProvider.value = {}
    microvmSubstrate.value = {}
    return
  }

  await Promise.all(selectedRangeProviders.value.map(loadRangeImagesForProvider))

  const selected = new Set(selectedRangeProviders.value)
  rangeImagesByProvider.value = Object.fromEntries(
    Object.entries(rangeImagesByProvider.value).filter(([provider]) => selected.has(provider))
  )

  if (selected.has('microvm')) {
    try {
      microvmSubstrate.value = await apiGet('/plugin/range/microvm/substrate-status')
    } catch (e) {
      microvmSubstrate.value = {}
    }
  } else {
    microvmSubstrate.value = {}
  }
}

async function loadRangeFeatures() {
  try {
    const data = await apiGet('/plugin/range/onprem/features')
    rangeFeatures.value = data || { default: [], custom: [] }
  } catch (e) {
    rangeFeatures.value = { default: [], custom: [] }
  }
}

async function loadPlanExecuteContextSources() {
  if (!isPlanExecute.value) return
  await loadPlanStixFiles()
  await loadRangeProviders()
  await loadRangeFeatures()
  await loadRangeImages()
  emitPlanContext()
}

function emitPlanContext() {
  if (!isPlanExecute.value) {
    emit('update:workflowContext', {})
    return
  }
  emit('update:workflowContext', {
    selected_stix_files: selectedPlanStix.value,
    cti_uses_rag: selectedPlanStix.value.length > 0,
    cti_rag_model: selectedPlanStix.value.length ? ctiRagModel.value.trim() : '',
    cti_rag_api_base: selectedPlanStix.value.length ? ctiRagApiBase.value.trim() : '',
    cti_rag_api_key: selectedPlanStix.value.length ? ctiRagApiKey.value : '',
    cti_rag_ssl_verify: selectedPlanStix.value.length ? ctiRagSslVerify.value : null,
    cti_rag_topk: selectedPlanStix.value.length ? ctiRagTopk.value : null,
    cti_rag_temperature: selectedPlanStix.value.length ? ctiRagTemperature.value : null,
    cti_rag_max_tool_calls: selectedPlanStix.value.length ? ctiRagMaxToolCalls.value : null,
    cti_rag_max_tokens: selectedPlanStix.value.length ? ctiRagMaxTokens.value : null,
    build_range: buildRange.value,
    range_provider: buildRange.value ? rangeProvider.value : '',
    range_providers: buildRange.value ? selectedRangeProviders.value : [],
    identity_options: {
      domain: identityDomain.value,
      domain_users: identityDomainUsers.value,
      local_users: identityLocalUsers.value,
    },
    agent_start: {
      mode: agentMode.value,
      use_cti_entry_host: agentUseCtiEntry.value,
    },
    range_capabilities: {
      providers: rangeProviders.value,
      features: rangeFeatures.value,
      images: rangeImages.value,
      image_count: rangeImages.value.length,
      images_by_provider: rangeImagesByProvider.value,
      microvm_substrate: microvmSubstrate.value,
    },
  })
}

onMounted(loadPlanExecuteContextSources)
watch(isPlanExecute, loadPlanExecuteContextSources)
watch(selectedRangeProviders, loadRangeImages, { deep: true })
watch(
  [
    selectedPlanStix, buildRange, selectedRangeProviders, rangeProviders, rangeImagesByProvider,
    rangeFeatures, microvmSubstrate, identityDomain, identityDomainUsers,
    identityLocalUsers, agentMode, agentUseCtiEntry, ctiRagModel,
  ],
  emitPlanContext,
  { deep: true },
)
</script>

<style scoped>
.chat-sidebar {
  position: relative;
  width: 390px;
  flex-shrink: 0;
  height: 100%;
  background-color: #1c1a22;
  border-left: 1px solid rgba(158, 98, 255, 0.3);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
  overflow: hidden;
}
.chat-sidebar.collapsed { width: 44px; }
.sidebar-header {
  /* Mirrors .chat-header on the left so the bottom border reads as one
     continuous line across the top of the screen and the collapse-toggle
     sits at the same vertical centerline as the Back button + workflow
     title in the chat header. */
  display: flex;
  align-items: center;
  padding: 0.5rem 0.85rem;
  background-color: #17131f;
  border-bottom: 1px solid rgba(158, 98, 255, 0.24);
  flex-shrink: 0;
}
.collapse-toggle {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  background: rgba(139, 92, 246, 0.12);
  border: 1px solid rgba(169, 112, 255, 0.52);
  color: #f5f1ff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
}
.collapse-toggle:hover {
  background-color: rgba(169, 112, 255, 0.2);
  border-color: #b98cff;
}
.sidebar-body {
  padding: 0.9rem 1rem 1.2rem 1rem;
  overflow-y: auto;
  flex: 1;
}
.sidebar-section {
  margin-top: 0.95rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(158, 98, 255, 0.18);
}
.sidebar-section:first-child {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}
.section-title {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #c9b8ff;
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
  flex-wrap: nowrap;
  min-width: 0;
}
.check-row input[type="checkbox"] {
  accent-color: #a970ff;
  flex-shrink: 0;
}
.check-name { color: #f5f5f5; }
.check-meta {
  color: #a99dbe;
  font-size: 0.72rem;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.check-row.compact {
  gap: 0.4rem;
  font-size: 0.78rem;
}
.picker-toggle {
  width: 100%;
  min-height: 30px;
  border: 1px solid rgba(169, 112, 255, 0.35);
  border-radius: 4px;
  background: #24202e;
  color: #f5f5f5;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0 0.55rem;
  cursor: pointer;
}
.picker-toggle .check-meta { margin-left: auto; }
.picker-toggle:hover {
  background: #2e2740;
  border-color: #a970ff;
}
.model-toggle .check-meta {
  max-width: 205px;
  white-space: nowrap;
}
.truncate {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.selected-copy .truncate {
  flex: 0 1 auto;
}
.empty-row,
.error-row {
  font-size: 0.78rem;
  color: #a99dbe;
  padding: 0.35rem 0;
}
.error-row { color: #e58b8b; }
.cti-rag-panel {
  margin-top: 0.55rem;
  border: 1px solid rgba(169, 112, 255, 0.24);
  border-radius: 6px;
  background: rgba(139, 92, 246, 0.07);
  padding: 0.65rem;
}
.helper-row {
  color: #a99dbe;
  font-size: 0.72rem;
  line-height: 1.35;
}
.field-stack {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.field-stack.tight { gap: 0.3rem; }
.field-label {
  font-size: 0.72rem;
  color: #c9b8ff;
}
.compact-select,
.compact-input {
  width: 100%;
  min-height: 30px;
  border-radius: 4px;
  border: 1px solid rgba(169, 112, 255, 0.3);
  background: #17151d;
  color: #f5f5f5;
  padding: 0 0.45rem;
  outline: none;
}
.compact-select:focus,
.compact-input:focus {
  border-color: #a970ff;
  box-shadow: 0 0 0 2px rgba(169, 112, 255, 0.18);
}
.model-config-panel {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  border: 1px solid rgba(169, 112, 255, 0.24);
  border-radius: 6px;
  background: rgba(139, 92, 246, 0.07);
  padding: 0.65rem;
}
.model-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.45rem;
}
.model-grid label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.profile-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 0.35rem;
  align-items: stretch;
}
.profile-actions .compact-input {
  min-width: 0;
}
.mini-button {
  min-height: 30px;
  border: 1px solid rgba(169, 112, 255, 0.32);
  border-radius: 4px;
  background: #24202e;
  color: #f5f1ff;
  padding: 0 0.55rem;
  cursor: pointer;
}
.mini-button.primary {
  border-color: rgba(45, 212, 191, 0.5);
  background: rgba(45, 212, 191, 0.15);
  color: #e9fffb;
}
.mini-button:hover:not(:disabled) {
  border-color: #a970ff;
  background: rgba(169, 112, 255, 0.18);
}
.mini-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.capability-line {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  color: #a99dbe;
  font-size: 0.72rem;
}
.capability-line span {
  border: 1px solid rgba(169, 112, 255, 0.28);
  border-radius: 4px;
  background: rgba(139, 92, 246, 0.08);
  color: #d8d1e8;
  padding: 0.12rem 0.35rem;
}
.identity-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.25rem;
  color: #d8d8d8;
  font-size: 0.78rem;
}
.identity-grid input { accent-color: #a970ff; }
.selected-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.selected-row,
.provider-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  border: 1px solid rgba(169, 112, 255, 0.24);
  border-radius: 4px;
  background: #201d27;
  padding: 0.35rem 0.45rem;
}
.provider-row { align-items: flex-start; }
.provider-row.selected {
  border-color: rgba(169, 112, 255, 0.75);
  background: rgba(139, 92, 246, 0.13);
}
.selected-copy {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 0;
  flex: 1 1 auto;
}
.remove-chip,
.modal-close {
  width: 26px;
  height: 26px;
  border: 1px solid rgba(169, 112, 255, 0.35);
  border-radius: 4px;
  background: #24202e;
  color: #f5f1ff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}
.remove-chip:hover,
.modal-close:hover {
  background: rgba(169, 112, 255, 0.2);
  border-color: #a970ff;
  color: #ffffff;
}
.modal-scrim {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.62);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}
.stix-modal {
  width: min(980px, calc(100vw - 3rem));
  max-height: min(720px, calc(100vh - 3rem));
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(169, 112, 255, 0.45);
  border-radius: 6px;
  background: #1c1a22;
  color: #f5f5f5;
  box-shadow: 0 18px 55px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(139, 92, 246, 0.12);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.1rem;
  border-bottom: 1px solid rgba(169, 112, 255, 0.2);
}
.modal-header h3 {
  font-size: 1rem;
  line-height: 1.2;
  margin: 0;
  color: #f5f5f5;
}
.modal-header p {
  margin: 0.25rem 0 0 0;
  color: #a99dbe;
  font-size: 0.78rem;
}
.modal-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.7rem 1.1rem;
  border-bottom: 1px solid rgba(169, 112, 255, 0.18);
  color: #d8d1e8;
  font-size: 0.78rem;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.toolbar-actions button {
  min-height: 28px;
  border: 1px solid rgba(169, 112, 255, 0.35);
  border-radius: 4px;
  background: #24202e;
  color: #d8d8d8;
  padding: 0 0.65rem;
  cursor: pointer;
}
.toolbar-actions button:hover {
  background: #2e2740;
  border-color: #a970ff;
}
.stix-table-wrap {
  overflow: auto;
  min-height: 220px;
}
.stix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.stix-table th,
.stix-table td {
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid rgba(169, 112, 255, 0.14);
  text-align: left;
  vertical-align: middle;
}
.stix-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #24202e;
  color: #d8d1e8;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.stix-table tbody tr {
  cursor: pointer;
}
.stix-table tbody tr:hover,
.stix-table tbody tr.selected {
  background: rgba(139, 92, 246, 0.13);
}
.stix-table input[type="checkbox"] {
  accent-color: #a970ff;
}
.select-col {
  width: 84px;
}
.file-cell {
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.right { text-align: right !important; }
.empty-cell {
  color: #888888;
  text-align: center !important;
  padding: 2.5rem 1rem !important;
}
@media (max-width: 720px) {
  .modal-scrim { padding: 0.75rem; }
  .stix-modal {
    width: calc(100vw - 1.5rem);
    max-height: calc(100vh - 1.5rem);
  }
  .stix-table th:nth-child(3),
  .stix-table td:nth-child(3),
  .stix-table th:nth-child(4),
  .stix-table td:nth-child(4) {
    display: none;
  }
  .file-cell { max-width: 48vw; }
}
</style>
