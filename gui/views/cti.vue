<!-- CTI Ingest Page -->
<template>
  <div class="content">
    <div class="columns" style="margin: 0 1rem;">

      <!-- LEFT: CTI INGEST -->
      <div class="column is-two-thirds">
        <div class="box">
          <div class="is-flex is-justify-content-space-between mb-4">
            <h2 class="title is-4 has-text-primary">CTI Ingest Pipeline</h2>
            <button class="button is-light is-small" @click="$emit('back')">
              ← Back
            </button>
          </div>

          <p class="mb-4">
            Upload raw CTI reports (.txt, .md, .html). The pipeline extracts entities,
            behaviors, MITRE techniques, and produces STIX for RAG.
          </p>

          <input
            ref="ctiFileInput"
            type="file"
            class="input"
            accept=".txt,.md,.html,.pdf" 
            @change="onCtiFileSelected"
          />

          <div class="is-flex is-justify-content-flex-end mt-4">
            <button
              class="button is-primary"
              :disabled="!ctiFile"
              @click="uploadCti"
            >
              Upload CTI
            </button>
          </div>

          <div v-if="ctiStatus" class="notification is-info mt-4">
            {{ ctiStatus }}
          </div>
        </div>
      </div>

      <!-- RIGHT: CTI MODEL CONFIG -->
      <div class="column is-one-third">
        <div class="box" style="position: sticky; top: 1rem;">

          <!-- Header / Toggle -->
          <div
            class="is-flex is-justify-content-space-between is-align-items-center mb-3"
            style="cursor: pointer;"
            @click="useOverride = !useOverride"
          >
            <h3 class="title is-5 has-text-primary mb-0">
              CTI Model Override
            </h3>

            <span class="icon">
              <svg v-if="useOverride" viewBox="0 0 448 512">
                <path fill="currentColor"
                  d="M432 256c0 17.7-14.3 32-32 32H48c-17.7 0-32-14.3-32-32s14.3-32 32-32h352c17.7 0 32 14.3 32 32z" />
              </svg>
              <svg v-else viewBox="0 0 448 512">
                <path fill="currentColor"
                  d="M256 80c17.7 0 32 14.3 32 32v112h112c17.7 0 32 14.3 32 32s-14.3 32-32 32H288v112c0 17.7-14.3 32-32 32s-32-14.3-32-32V288H112c-17.7 0-32-14.3-32-32s14.3-32 32-32h112V112c0-17.7 14.3-32 32-32z" />
              </svg>
            </span>
          </div>

          <!-- Override Content -->
          <div v-if="useOverride">
            <!-- Provider -->
            <div class="field">
              <label class="label">Provider</label>
              <input class="input" v-model="overrideConfig.provider" />
            </div>

            <!-- Model -->
            <div class="field">
              <label class="label">Model</label>
              <input class="input" v-model="overrideConfig.model" />
            </div>

            <!-- API Base -->
            <div class="field">
              <label class="label">API Base URL</label>
              <input class="input" v-model="overrideConfig.api_base" />
            </div>

            <!-- API Key -->
            <div class="field">
              <label class="label">API Key</label>
              <input class="input" type="password" v-model="overrideConfig.api_key" />
            </div>
            
            <div class="field">
              <label class="label">Temperature</label>
              <input
                class="input"
                type="number"
                step="0.1"
                min="0"
                max="1"
                v-model.number="overrideConfig.temperature"
              />
            </div>

            <div class="field">
              <label class="label">Top-P</label>
              <input
                class="input"
                type="number"
                step="0.1"
                min="0"
                max="1"
                v-model.number="overrideConfig.top_p"
              />
            </div>

            <div class="field">
              <label class="checkbox">
                <input type="checkbox" v-model="overrideConfig.stream" />
                Stream responses
              </label>
            </div>
            <!-- Flags -->
            <div class="field">
              <label class="checkbox">
                <input type="checkbox" v-model="overrideConfig.offline" />
                Offline mode
              </label>
            </div>

            <div class="field">
              <label class="checkbox">
                <input type="checkbox" v-model="overrideConfig.use_mock" />
                Use mock responses
              </label>
            </div>

            <!-- Timeout -->
            <div class="field">
              <label class="label">Timeout (seconds)</label>
              <input class="input" type="number" v-model.number="overrideConfig.timeout" />
            </div>

            <!-- Max Tokens -->
            <div class="field">
              <label class="label">Max Tokens</label>
              <input class="input" type="number" v-model.number="overrideConfig.max_tokens" />
            </div>
          </div>
          <div class="is-flex is-justify-content-flex-end mt-3">
            <button
              class="button is-success is-small"
              :disabled="!useOverride"
              @click="saveCTIConfig"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="box mt-4">
      <h3 class="title is-6">Raw CTI Inputs</h3>

      <table class="table is-fullwidth is-striped is-hoverable">
        <thead>
          <tr>
            <th></th>
            <th>File</th>
            <th>Status</th>
            <th class="has-text-right">Size</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in visibleRows"
            :key="row._rowKey"
            @click="row._kind === 'parent' && row.type === 'dir' && toggleDir(row.name)"
          >
            <td>
              <input
                type="checkbox"
                @click.stop
                @change="toggleRawSelection(row)"
                :checked="isRowSelected(row)"
              />
            </td>

            <td>
              <span v-if="row._kind === 'parent' && row.type === 'dir'">
                {{ expandedDirs[row.name] ? '📂' : '📁' }} {{ row.name }}
              </span>

              <span v-else-if="row._kind === 'parent'">
                📄 {{ row.name }}
              </span>

              <span v-else class="pl-5">
                📄 {{ row.name }}
              </span>
            </td>
            <td>
              <span
                v-if="row.type === 'file'"
                class="tag"
                :class="row.status === 'processed' ? 'is-success' : 'is-warning'"
              >
                {{ row.status || 'pending'}}
              </span>
            </td>
            <td class="has-text-right">
              {{ row.size ? (row.size / 1024).toFixed(1) + ' KB' : '—' }}
            </td>
          </tr>
        </tbody>

      </table>
      <div class="buttons">
        <button
          class="button is-primary is-small"
          :disabled="!selectedRaw.size"
          @click="runPipelineForSelected"
        >
          Run Pipeline
        </button>
        <button
          class="button is-danger is-small"
          :disabled="!selectedRaw.size"
          @click="deleteSelected"
        >
          Delete Selected CTI
        </button>
      </div>
    </div>
    <div class="box mt-4">
      <h3 class="title is-6">Generated STIX Objects</h3>

      <table class="table is-fullwidth is-striped is-hoverable">
        <thead>
          <tr>
            <th>File</th>
            <th>Model</th>
            <th class="has-text-right">Size</th>
            <th style="width: 70px;">View</th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="f in stixFiles" :key="f.name">
            <td>
              <input
                type="checkbox"
                :checked="selectedStix.has(f.name)"
                @change="e => {
                  e.target.checked
                    ? selectedStix.add(f.name)
                    : selectedStix.delete(f.name)
                }"
              />
              📦 {{ f.name }}
            </td>
            <td>
              <span class="has-text-grey" v-if="!f.model">
                {{ (f.model) }}
              </span>
              <span v-else>{{ f.provider ? `${f.provider} / ${f.model}` : f.model }}</span>
            </td>
            <td class="has-text-right">
              {{ (f.size / 1024).toFixed(1) }} KB
            </td>
            <!-- VIEW BUTTON -->
            <td>
              <div class="buttons is-centered are-small">
              <button
                class="button is-primary is-small is-light"
                @click.stop="viewStix(f.name)"
              >
                View
              </button>
              </div>
            </td>
          </tr>

          <tr v-if="!stixFiles.length">
            <td colspan="2" class="has-text-grey has-text-centered">
              No STIX objects generated yet
            </td>
          </tr>
        </tbody>
      </table>
      <div class="buttons">
        <button
          class="button is-primary is-small"
          :disabled="!selectedStix.size"
          @click="downloadStix(Array.from(selectedStix))"
        >
          Download Selected
        </button>

        <button
          class="button is-danger is-small"
          :disabled="!selectedStix.size"
          @click="deleteStix"
        >
          Delete Selected STIX
        </button>
      </div>

    </div>
      <StixViewerModal
      v-if="showStixModal"
      :filename="stixFilename"
      :stix="stixData"
      @close="showStixModal = false"
    />

  </div>
  
</template>

<script setup>
import { ref, reactive, onMounted, watch, computed } from 'vue'
import StixViewerModal from './stixViewer.vue'
/* ---------------------------------
 * UI state
 * --------------------------------- */
const emit = defineEmits(['back'])
const useOverride = ref(false)
const ctiFileInput = ref(null)

const ctiFile = ref(null)
const ctiStatus = ref('')
const rawFiles = ref([])
const selectedRaw = reactive(new Set())
const stixFiles = ref([])
const selectedStix = reactive(new Set())

// STIX viewer modal state
const showStixModal = ref(false)
const stixData = ref(null)
const stixFilename = ref('')

/* ---------------------------------
 * Config state
 * --------------------------------- */
const backendConfig = ref(null)
const overrideConfig = reactive({
  provider: null,
  model: null,
  api_key: null,
  api_base: null,

  offline: false,
  use_mock: false,

  timeout: 120,
  max_tokens: 4000,
  temperature: 0.0,
  top_p: 1.0,
  stream: false
})

const effectiveConfig = computed(() =>
  useOverride.value ? overrideConfig : backendConfig.value || {}
)

const expandedDirs = ref({})

const visibleRows = computed(() => {
  const rows = []

  for (const item of rawFiles.value) {
    // parent row
    rows.push({
      ...item,
      _kind: 'parent',
      _rowKey: item.name
    })

    // child rows (only if expanded and children exist)
    if (item.type === 'dir' && expandedDirs.value[item.name] && Array.isArray(item.children)) {
      for (const child of item.children) {
        rows.push({
          ...child,
          _kind: 'child',
          _parent: item.name,
          _rowKey: `${item.name}/${child.name}`
        })
      }
    }
  }

  return rows
})

function toggleDir(name) {
  expandedDirs.value = {
    ...expandedDirs.value,
    [name]: !expandedDirs.value[name]
  }
  console.log('[expandedDirs]', expandedDirs.value)
  console.log('[visibleRows AFTER toggle]', visibleRows.value.length)
}

function itemPath(dirName, childName) {
  return `${dirName}/${childName}`
}

/* ---------------------------------
 * Raw CTI file handling
 * --------------------------------- */
async function loadRawFiles() {
  const res = await fetch('/plugin/mcp/cti/raw')
  const data = await res.json()
  rawFiles.value = (data.items || [])
  .map(item => {
    if (item.type === 'dir') {
      const kids = item.children || []

      return {
        ...item,
        // keep children, but make it safe to render
        children: kids
      }
    }
    return item
  })
  .sort((a, b) => {
    if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  console.log('[RAW ITEMS]', data.items)

}

async function deleteSelected() {
  if (!selectedRaw.size) return

  await fetch('/plugin/mcp/cti/raw/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: Array.from(selectedRaw) })
  })

  selectedRaw.clear()
  loadRawFiles()
}

function onCtiFileSelected(e) {
  ctiFile.value = e.target.files[0]
}

function isRowSelected(row) {
  if (row._kind === 'parent') {
    return selectedRaw.has(row.name)
  }
  return selectedRaw.has(itemPath(row._parent, row.name))
}

function toggleRawSelection(row) {
  selectedRaw.has(row.name)
    ? selectedRaw.delete(row.name)
    : selectedRaw.add(row.name)
}
/* ---------------------------------
 * Config loading (CTI → LLM fallback)
 * --------------------------------- */
async function loadBackendConfig() {
  const res = await fetch('/plugin/mcp/get_config')
  if (!res.ok) throw new Error('Failed to load config')

  const data = await res.json()
  console.log('[CTI] Raw get_config response:', data)

  const cfg = data?.config ?? data ?? {}

  // 🔑 AUTHORITATIVE FALLBACK ORDER
  const cti = cfg.cti ?? cfg.llm ?? {}

  backendConfig.value = {
    provider: cti.provider ?? null,
    model: cti.model ?? null,
    api_key: cti.api_key ?? null,
    api_base: cti.api_base ?? null,

    offline: cti.offline ?? false,
    use_mock: cti.use_mock ?? false,

    timeout: cti.timeout ?? 120,
    max_tokens: cti.max_tokens ?? 4000,
    temperature: cti.temperature ?? 0.0,
    top_p: cti.top_p ?? 1.0,
    stream: cti.stream ?? false
  }

  console.log('[CTI] Backend config resolved:', backendConfig.value)
}

function initOverridesFromBackend() {
  if (!backendConfig.value) return

  for (const [k, v] of Object.entries(backendConfig.value)) {
    if (overrideConfig[k] === undefined || overrideConfig[k] === null) {
      overrideConfig[k] = v
    }
  }
}

/* ---------------------------------
 * Persist override (explicit)
 * --------------------------------- */
async function saveCTIConfig() {
  const payload = {
    llm: {
      provider: overrideConfig.provider,
      model: overrideConfig.model,
      api_base: overrideConfig.api_base,
      api_key: overrideConfig.api_key,
      temperature: overrideConfig.temperature,
      top_p: overrideConfig.top_p,
      max_tokens: overrideConfig.max_tokens,
      timeout: overrideConfig.timeout,
      stream: overrideConfig.stream,
      offline: overrideConfig.offline,
      use_mock: overrideConfig.use_mock
    }
  }

  await fetch('/plugin/mcp/set_config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })

  // reload from disk to prove persistence
  await loadBackendConfig()
  initOverridesFromBackend()
}

/* ---------------------------------
 * Upload CTI
 * --------------------------------- */
async function uploadCti() {
  const form = new FormData()
  form.append('file', ctiFile.value)

  if (useOverride.value) {
    form.append('config', JSON.stringify(overrideConfig))
  }

  ctiStatus.value = 'Uploading CTI…'

  const res = await fetch('/plugin/mcp/cti/upload', {
    method: 'POST',
    body: form
  })

  const data = await res.json()
  if (!res.ok) throw new Error(data.error)

  ctiStatus.value = 'Raw CTI ingestion successfull.'
  ctiFile.value = null
  if (ctiFileInput.value) {
    ctiFileInput.value.value = ''
  }
  loadRawFiles()
}

async function loadStixFiles() {
  const res = await fetch('/plugin/mcp/stix/list')
  if (!res.ok) return

  const data = await res.json()

  stixFiles.value = (data.files || [])
    .filter(f => f.filename.endsWith('.json'))
    .map(f => ({
      name: f.filename,
      size: f.size,
      model: f.model || null,
      provider: f.provider || null
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

async function deleteStix() {
  if (!selectedStix.size) return

  await fetch('/plugin/mcp/stix/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: Array.from(selectedStix) })
  })

  selectedStix.clear()
  loadStixFiles()
}

async function downloadStix(target) {
  const files = Array.isArray(target) ? target : [target]
  if (!files.length) return

  for (const filename of files) {
    const res = await fetch('/plugin/mcp/stix/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename })
    })

    if (!res.ok) {
      const err = await res.json()
      console.error('[STIX DOWNLOAD FAILED]', filename, err)
      continue
    }

    const blob = await res.blob()
    const url = window.URL.createObjectURL(blob)

    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()

    a.remove()
    window.URL.revokeObjectURL(url)
  }
}

async function runPipelineForSelected() {
  if (!selectedRaw.size) return

  await fetch('/plugin/mcp/cti/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: Array.from(selectedRaw),
      step: 'all',
      config: useOverride.value ? overrideConfig : null
    })
  })

  ctiStatus.value = 'CTI pipeline started for selected files.'
  selectedRaw.clear()


  // refresh raw immediately
  loadRawFiles()

  // poll STIX until new files appear (max ~60s)
  const start = Date.now()
  const poll = setInterval(async () => {
    await loadStixFiles()

    if (stixFiles.value.length > 0 || Date.now() - start > 60000) {
      clearInterval(poll)
    }
  }, 2000)
}

// Single stix view modal
async function viewStix(filename) {
  const res = await fetch('/plugin/mcp/stix/get_stix', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename })
  })

  const out = await res.json()
  if (!res.ok) throw new Error(out?.error || 'Failed to load STIX')

  stixData.value = out.data
  stixFilename.value = out.filename
  showStixModal.value = true
}

/* ---------------------------------
 * Lifecycle
 * --------------------------------- */
onMounted(async () => {
  await loadBackendConfig()
  initOverridesFromBackend()
  loadRawFiles()
  loadStixFiles()
})

</script>
