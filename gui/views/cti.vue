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

          <!-- Upload. The whole zone is a drop target; the hidden input is
               kept so keyboard and screen-reader users still get a real
               file picker. -->
          <div
            class="cti-dropzone"
            :class="{ 'is-dragging': isDragging, 'has-file': !!ctiFile }"
            role="button"
            tabindex="0"
            @click="ctiFileInput.click()"
            @keydown.enter.prevent="ctiFileInput.click()"
            @keydown.space.prevent="ctiFileInput.click()"
            @dragenter.prevent="onDragEnter"
            @dragover.prevent
            @dragleave="onDragLeave"
            @drop.prevent="onDrop"
          >
            <p v-if="ctiFile" class="cti-dropzone__file">
              {{ ctiFile.name }}
              <span class="cti-dropzone__size">
                {{ (ctiFile.size / 1024).toFixed(1) }} KB
              </span>
            </p>
            <p v-else class="cti-dropzone__copy">
              Drop a report here, or <span class="cti-dropzone__link">browse</span>
            </p>
            <p class="cti-dropzone__hint">TXT, MD, HTML or PDF</p>
          </div>

          <p v-if="ctiDropError" class="help is-danger mt-2">{{ ctiDropError }}</p>

          <input
            ref="ctiFileInput"
            type="file"
            class="is-hidden"
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
const isDragging = ref(false)
const dragDepth = ref(0)
const ctiDropError = ref('')
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
    offline: cti.offline ?? false
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

// Mirrors the extension check in mcp_api.upload_cti_raw. Rejecting here keeps
// an unsupported file from becoming a 400 the operator has to interpret.
const CTI_EXTENSIONS = ['.txt', '.md', '.html', '.pdf']

function acceptCtiFile(file) {
  ctiDropError.value = ''
  if (!file) return
  const name = (file.name || '').toLowerCase()
  if (!CTI_EXTENSIONS.some(ext => name.endsWith(ext))) {
    ctiDropError.value = `${file.name} is not a supported type. Use TXT, MD, HTML or PDF.`
    ctiFile.value = null
    return
  }
  ctiFile.value = file
}

function onCtiFileSelected(e) {
  acceptCtiFile(e.target.files[0])
}

function onDragEnter() {
  dragDepth.value += 1
  isDragging.value = true
}

function onDragLeave() {
  // dragleave also fires when the cursor crosses a child element, so track
  // depth rather than clearing on the first one.
  dragDepth.value -= 1
  if (dragDepth.value <= 0) {
    dragDepth.value = 0
    isDragging.value = false
  }
}

function onDrop(e) {
  dragDepth.value = 0
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (!files || !files.length) return
  if (files.length > 1) {
    ctiDropError.value = 'Drop one file at a time.'
    return
  }
  acceptCtiFile(files[0])
  // The hidden input still holds any earlier pick, so clear it to keep the
  // two entry points from disagreeing about what is staged.
  if (ctiFileInput.value) ctiFileInput.value.value = ''
}

async function uploadCti() {
  const form = new FormData()
  form.append('file', ctiFile.value)

  ctiStatus.value = 'Uploading CTI…'

  const res = await fetch('/plugin/mcp/cti/upload', {
    method: 'POST',
    body: form
  })

  if (!res.ok) {
    ctiStatus.value = `Upload failed (${res.status}).`
    return
  }

  // Staged only. Nothing is extracted until Run Pipeline.
  ctiStatus.value = 'File staged. Select it and press Run Pipeline to extract.'
  ctiFile.value = null
  ctiDropError.value = ''
  if (ctiFileInput.value) ctiFileInput.value.value = ''

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
  const count = selectedRaw.size
  if (!count) {
    ctiStatus.value = 'Select a file first.'
    return
  }

  ctiStatus.value = 'Starting pipeline…'

  let res
  try {
    res = await fetch('/plugin/mcp/cti/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: Array.from(selectedRaw), step: 'all' })
    })
  } catch (e) {
    ctiStatus.value = `Could not reach the server: ${e.message}`
    return
  }

  // The handler rejects an empty or malformed file list with a 400, which
  // this used to report as success.
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).error || '' } catch { /* non-JSON body */ }
    ctiStatus.value = `Pipeline did not start (${res.status})${detail ? ': ' + detail : ''}.`
    return
  }

  // Accepted, not finished: extraction runs in the background and the file
  // stays "pending" until its IR lands. Failures appear in the caldera log.
  ctiStatus.value =
    `Pipeline running on ${count} file${count === 1 ? '' : 's'}. ` +
    'Status updates when extraction completes; check the server log for errors.'
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

.cti-dropzone {
  border: 1px dashed rgba(158, 98, 255, 0.45);
  border-radius: 8px;
  background-color: #242424;
  padding: 1.75rem 1rem;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}
.cti-dropzone:hover,
.cti-dropzone:focus-visible {
  border-color: rgba(158, 98, 255, 0.8);
  background-color: #2a2730;
}
/* The browser paints no drag feedback of its own, so the lift has to be
   obvious enough to read as a valid target mid-drag. */
.cti-dropzone.is-dragging {
  border-color: #9e62ff;
  border-style: solid;
  background-color: #2f2838;
}
.cti-dropzone.has-file {
  border-style: solid;
  border-color: rgba(72, 199, 142, 0.6);
}
.cti-dropzone__copy,
.cti-dropzone__file {
  margin: 0;
  color: #f5f5f5;
  word-break: break-all;
}
.cti-dropzone__link {
  color: #9e62ff;
  text-decoration: underline;
}
.cti-dropzone__size {
  color: #a0a0a0;
  margin-left: 0.4rem;
  white-space: nowrap;
}
.cti-dropzone__hint {
  margin: 0.35rem 0 0;
  font-size: 0.75rem;
  color: #a0a0a0;
}

/* Pointer-events off so a drag over the filename does not fire dragleave on
   the zone, which would flicker the highlight. */
.cti-dropzone * {
  pointer-events: none;
}
</style>
