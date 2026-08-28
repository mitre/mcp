<!-- ============================================================
     CTI INGEST PAGE
     ============================================================ -->
<template>
  <div class="content cti-page">
    <div class="columns">

      <!-- =====================================================
           LEFT: CTI INGEST + FILE TABLES
           ===================================================== -->
      <div class="column is-two-thirds">
        <div class="box">

          <!-- Header -->
          <div class="is-flex is-justify-content-space-between mb-4">
            <h2 class="title is-4 has-text-primary">CTI Ingest Pipeline</h2>
            <button class="button is-light is-small" @click="$emit('back')">
              ← Back
            </button>
          </div>

          <p class="mb-4">
            Upload raw Cyber Threat Intelligence reports. The pipeline extracts
            entities, behaviors, MITRE techniques, and produces STIX for RAG.
          </p>

          <!-- Upload -->
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

        <!-- =====================================================
             RAW CTI FILES
             ===================================================== -->
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
                  <span v-else-if="row._kind === 'parent'">📄 {{ row.name }}</span>
                  <span v-else class="pl-5">📄 {{ row.name }}</span>
                </td>

                <td>
                  <span
                    v-if="row.type === 'file'"
                    class="tag"
                    :class="row.status === 'processed' ? 'is-success' : 'is-warning'"
                  >
                    {{ row.status || 'pending' }}
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
              @click="deleteSelectedRaw"
            >
              Delete Selected
            </button>
          </div>
        </div>

        <!-- =====================================================
             GENERATED STIX
             ===================================================== -->
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
                    @change="toggleStixSelection(f.name)"
                  />
                  📦 {{ f.name }}
                </td>

                <td class="has-text-grey">
                  {{ f.provider ? `${f.provider} / ${f.model}` : f.model || '—' }}
                </td>

                <td class="has-text-right">
                  {{ (f.size / 1024).toFixed(1) }} KB
                </td>

                <td>
                  <button
                    class="button is-primary is-small is-light"
                    @click.stop="viewStix(f.name)"
                  >
                    View
                  </button>
                </td>
              </tr>

              <tr v-if="!stixFiles.length">
                <td colspan="4" class="has-text-grey has-text-centered">
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
              Delete Selected
            </button>
          </div>
        </div>
      </div>

      <!-- =====================================================
           RIGHT: CTI EXTRACTION MODEL (sticky sidebar)
           ===================================================== -->
      <div class="column is-one-third">
        <McpModelConfigPanel
          :backend-config="backendConfig ?? {}"
          config-key="cti"
          title="CTI Extraction Model"
          @saved="loadBackendConfig"
        />
      </div>
    </div>

    <!-- STIX VIEWER -->
    <StixViewerModal
      v-if="showStixModal"
      :filename="stixFilename"
      :stix="stixData"
      @close="showStixModal = false"
    />
  </div>
</template>

<script setup>
/* ============================================================
 * Imports
 * ============================================================ */
import { computed, onMounted, reactive, ref } from 'vue'
import StixViewerModal from '../components/stixViewer.vue'
import McpModelConfigPanel from '../components/modelSelector.vue'

/* ============================================================
 * State (Alphabetical)
 * ============================================================ */
const backendConfig = ref(null)
const ctiFile = ref(null)
const ctiFileInput = ref(null)
const ctiStatus = ref('')
const expandedDirs = ref({})
const rawFiles = ref([])
const selectedRaw = reactive(new Set())
const selectedStix = reactive(new Set())
const showStixModal = ref(false)
const stixData = ref(null)
const stixFilename = ref('')
const stixFiles = ref([])

/* ============================================================
 * Computed
 * ============================================================ */
const visibleRows = computed(() => {
  const rows = []

  for (const item of rawFiles.value) {
    rows.push({ ...item, _kind: 'parent', _rowKey: item.name })

    if (item.type === 'dir' && expandedDirs.value[item.name]) {
      for (const child of item.children || []) {
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

/* ============================================================
 * Helpers
 * ============================================================ */
function itemPath(parent, name) {
  return `${parent}/${name}`
}

function isRowSelected(row) {
  return row._kind === 'parent'
    ? selectedRaw.has(row.name)
    : selectedRaw.has(itemPath(row._parent, row.name))
}

function toggleDir(name) {
  expandedDirs.value[name] = !expandedDirs.value[name]
}

function toggleRawSelection(row) {
  const key = row._kind === 'parent'
    ? row.name
    : itemPath(row._parent, row.name)

  selectedRaw.has(key)
    ? selectedRaw.delete(key)
    : selectedRaw.add(key)
}

function toggleStixSelection(name) {
  selectedStix.has(name)
    ? selectedStix.delete(name)
    : selectedStix.add(name)
}

/* ============================================================
 * Config
 * ============================================================ */
async function loadBackendConfig() {
  const res = await fetch('/plugin/mcp/get_config')
  if (!res.ok) throw new Error('Failed to load config')

  const data = await res.json()
  const cfg = data?.config ?? data ?? {}
  const cti = cfg?.cti ?? {}

  // api_key is deliberately absent: get_config never returns one. The
  // *_env names are surfaced so the panel can say where the key and the
  // endpoint actually come from.
  backendConfig.value = {
    provider: cti.provider ?? null,
    model: cti.model ?? null,
    api_base: cti.api_base ?? '',
    api_base_env: cti.api_base_env ?? null,
    api_key_env: cti.api_key_env ?? null,
    temperature: cti.temperature ?? 0.0,
    max_tokens: cti.max_tokens ?? 4000,
    timeout: cti.timeout ?? 120,
    offline: cti.offline ?? false,
    use_mock: cti.use_mock ?? false
  }
}
/* ============================================================
 * API: Raw CTI
 * ============================================================ */
async function loadRawFiles() {
  const res = await fetch('/plugin/mcp/cti/raw')
  const data = await res.json()

  rawFiles.value = (data.items || []).sort((a, b) => {
    if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

async function deleteSelectedRaw() {
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

async function uploadCti() {
  const form = new FormData()
  form.append('file', ctiFile.value)

  ctiStatus.value = 'Uploading CTI…'

  const res = await fetch('/plugin/mcp/cti/upload', {
    method: 'POST',
    body: form
  })

  if (!res.ok) throw new Error('CTI upload failed')

  ctiStatus.value = 'Raw CTI ingestion successful.'
  ctiFile.value = null
  ctiFileInput.value.value = ''

  loadRawFiles()
}

/* ============================================================
 * API: STIX
 * ============================================================ */
async function loadStixFiles() {
  const res = await fetch('/plugin/mcp/stix/list')
  const data = await res.json()

  stixFiles.value = (data.files || [])
    .filter(f => f.filename.endsWith('.json'))
    .map(f => ({
      name: f.filename,
      size: f.size,
      model: f.model,
      provider: f.provider
    }))
}

async function deleteStix() {
  await fetch('/plugin/mcp/stix/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: Array.from(selectedStix) })
  })

  selectedStix.clear()
  loadStixFiles()
}

async function downloadStix(files) {
  for (const filename of files) {
    const res = await fetch('/plugin/mcp/stix/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename })
    })

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)

    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()

    URL.revokeObjectURL(url)
  }
}

async function viewStix(filename) {
  const res = await fetch('/plugin/mcp/stix/get_stix', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename })
  })

  const out = await res.json()
  stixData.value = out.data
  stixFilename.value = out.filename
  showStixModal.value = true
}

/* ============================================================
 * Pipeline Execution
 * ============================================================ */
async function runPipelineForSelected() {
  await fetch('/plugin/mcp/cti/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files: Array.from(selectedRaw), step: 'all' })
  })

  ctiStatus.value = 'CTI pipeline started.'
  selectedRaw.clear()

  loadRawFiles()
  loadStixFiles()
}

/* ============================================================
 * Lifecycle
 * ============================================================ */
onMounted(() => {
  loadRawFiles()
  loadStixFiles()
  loadBackendConfig()
})
</script>

<style scoped>
/* ============================================================
 * PAGE GUTTER
 *
 * Bulma's .columns carries -0.75rem side margins that its .column
 * padding cancels out, so this padding is the gutter every box on the
 * page ends up sharing. The previous `margin: 0 1rem` on .columns
 * overrode those negatives, pushing the columns 0.75rem further in
 * than the boxes below them.
 * ============================================================ */
.cti-page {
  padding: 0 1rem;
}
</style>
