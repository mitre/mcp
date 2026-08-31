<!-- ============================================================
     CTI INGEST PAGE
     ============================================================ -->
<template>
  <div class="content cti-page">
    <!-- Both columns stretch so the ingest box and the config panel share a
         baseline instead of the shorter one leaving a ragged edge. -->
    <div class="columns is-align-items-stretch">

      <!-- =====================================================
           LEFT: CTI INGEST
           ===================================================== -->
      <div class="column is-two-thirds is-flex">
        <div class="box is-flex-grow-1 cti-ingest">

          <!-- Header -->
          <div class="is-flex is-justify-content-space-between mb-4">
            <h2 class="title is-4 has-text-primary">CTI Ingest Pipeline</h2>
            <button class="button is-light is-small" @click="$emit('back')">
              ← Back
            </button>
          </div>

          <p class="mb-4">
            Upload raw Cyber Threat Intelligence reports. The pipeline
            extracts ATT&amp;CK techniques, the named threat actor and file hash
            observables, and emits a STIX 2.1 bundle.
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
      <div class="column is-one-third is-flex">
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
            <th class="select-col"></th>
            <th>File</th>
            <th>Status</th>
            <th class="has-text-right">Size</th>
            <th class="view-col">View</th>
          </tr>
        </thead>
        <tbody>
          <!-- A directory row expands; anything else toggles its own
               checkbox, so the whole row is the hit target rather than a
               13px box. -->
          <tr
            v-for="row in visibleRows"
            :key="row._rowKey"
            class="is-clickable-row"
            @click="onRawRowClick(row)"
          >
            <td class="select-col">
              <!-- Always selects, even on a directory row, where clicking
                   the row body expands instead. -->
              <input
                type="checkbox"
                @click.stop="toggleRawSelection(row)"
                :checked="isRowSelected(row)"
              />
            </td>

            <td class="file-cell">
              <span v-if="row._kind === 'parent' && row.type === 'dir'">
                <span class="dir-caret">{{ expandedDirs[row.name] ? '▾' : '▸' }}</span>
                {{ row.name }}
              </span>
              <span v-else-if="row._kind === 'parent'">{{ row.name }}</span>
              <span v-else class="pl-5">{{ row.name }}</span>
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
              {{ row.size ? (row.size / 1024).toFixed(1) + ' KB' : '-' }}
            </td>

            <td class="view-col">
              <button
                v-if="row.type === 'file'"
                class="button is-primary is-small is-light"
                @click.stop="viewRaw(row)"
              >
                View
              </button>
            </td>
          </tr>

          <tr v-if="!visibleRows.length">
            <td colspan="5" class="has-text-grey has-text-centered">
              No reports uploaded yet
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
            <th class="select-col"></th>
            <th>File</th>
            <th>Model</th>
            <th class="has-text-right">Size</th>
            <th class="view-col">View</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="f in stixFiles"
            :key="f.name"
            class="is-clickable-row"
            @click="toggleStixSelection(f.name)"
          >
            <td class="select-col">
              <input
                type="checkbox"
                :checked="selectedStix.has(f.name)"
                @click.stop="toggleStixSelection(f.name)"
              />
            </td>

            <td class="file-cell">{{ f.name }}</td>

            <td class="has-text-grey">
              <span v-if="f.model">{{ f.provider ? `${f.provider} / ${f.model}` : f.model }}</span>
              <span v-else-if="f.extractor === 'offline'">offline extractor</span>
              <span v-else>-</span>
            </td>

            <td class="has-text-right">
              {{ (f.size / 1024).toFixed(1) }} KB
            </td>

            <td class="view-col">
              <button
                class="button is-primary is-small is-light"
                @click.stop="viewStix(f.name)"
              >
                View
              </button>
            </td>
          </tr>

          <tr v-if="!stixFiles.length">
            <td colspan="5" class="has-text-grey has-text-centered">
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

    <!-- =====================================================
         RAW REPORT PREVIEW
         ===================================================== -->
    <div v-if="showRawModal" class="modal is-active">
      <div class="modal-background" @click="showRawModal = false"></div>

      <div class="modal-card raw-viewer">
        <header class="modal-card-head">
          <!-- Bulma gives .modal-card-title the flex-grow that pushes the
               close button to the right edge. Wrapping the title in a plain
               div loses it, which left the button beside the filename. -->
          <div class="raw-viewer__heading">
            <p class="modal-card-title is-size-6">{{ rawViewer.filename }}</p>
            <p class="raw-viewer__meta">
              {{ rawViewer.kind ? rawViewer.kind.toUpperCase() : '' }}
              <span v-if="rawViewer.size">
                &middot; {{ (rawViewer.size / 1024).toFixed(1) }} KB
              </span>
              <span v-if="rawViewer.kind === 'pdf'"> &middot; extracted text</span>
            </p>
          </div>
          <button
            class="raw-viewer__close"
            aria-label="Close preview"
            @click="showRawModal = false"
          >&times;</button>
        </header>

        <section class="modal-card-body">
          <p v-if="rawViewer.loading" class="has-text-grey">Loading…</p>
          <p v-else-if="rawViewer.error" class="has-text-danger">{{ rawViewer.error }}</p>
          <pre v-else class="raw-viewer__text">{{ rawViewer.text }}</pre>
        </section>

        <footer class="modal-card-foot is-justify-content-flex-end">
          <button class="button is-small" @click="showRawModal = false">Close</button>
        </footer>
      </div>
    </div>
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

const showRawModal = ref(false)
const rawViewer = reactive({
  filename: '', kind: '', size: 0, text: '', loading: false, error: '',
})

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

// A directory row has no selectable file of its own, so clicking it expands.
// Every other row selects, which makes the row the hit target instead of the
// checkbox alone.
function onRawRowClick(row) {
  if (row._kind === 'parent' && row.type === 'dir') {
    toggleDir(row.name)
    return
  }
  toggleRawSelection(row)
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
  // The server resolves this now: it layers the profiles and applies the env
  // indirection with the same code extraction runs. Doing it here meant a
  // second copy of the allowlist and no env resolution at all, so the panel
  // printed "not set" for an endpoint that came from MCP_LLM_API_BASE.
  const resolved = data?.resolved?.cti ?? {}

  // api_key is deliberately absent: the server strips it from both payloads.
  backendConfig.value = {
    api_base_env: resolved.api_base_env ?? null,
    api_key_env: resolved.api_key_env ?? null,
    // The editable generation settings, resolved so the inputs show what is
    // actually in force rather than only what local.yml happens to restate.
    // Shared with the global profile, so whatever the server resolved is the
    // number both panels must show.
    temperature: resolved.temperature,
    max_tokens: resolved.max_tokens,
    timeout: resolved.timeout ?? 120,
    offline: resolved.offline ?? false,
    // Read-only. A workload profile cannot override the connection, so this
    // is always what will run.
    resolved_model: resolved.model ?? null,
    resolved_api_base: resolved.api_base || null,
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
      provider: f.provider,
      extractor: f.extractor
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

// A nested row is addressed by "<dir>/<name>", the same key selection uses.
async function viewRaw(row) {
  const name = row._kind === 'parent' ? row.name : itemPath(row._parent, row.name)

  Object.assign(rawViewer, {
    filename: name, kind: '', size: 0, text: '', loading: true, error: '',
  })
  showRawModal.value = true

  try {
    const res = await fetch('/plugin/mcp/cti/raw/view', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: name })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
    Object.assign(rawViewer, {
      kind: data.kind, size: data.size, text: data.text, loading: false,
    })
  } catch (e) {
    Object.assign(rawViewer, { loading: false, error: e.message })
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

  // Accepted, not finished. The run happens in a background executor, so the
  // outcome is polled rather than awaited; without this a failure only ever
  // reached the server log and the row sat on "pending" forever.
  ctiStatus.value = `Pipeline running on ${count} file${count === 1 ? '' : 's'}…`
  selectedRaw.clear()
  pollCtiStatus()
}

// Bounded so a wedged run stops the poll rather than hitting the endpoint
// until the tab closes.
const CTI_POLL_INTERVAL_MS = 2000
const CTI_POLL_LIMIT = 150

async function pollCtiStatus(attempt = 0) {
  if (attempt >= CTI_POLL_LIMIT) {
    ctiStatus.value =
      'Still running after 5 minutes. Check the server log; the page will not ' +
      'update further.'
    return
  }

  await new Promise(r => setTimeout(r, CTI_POLL_INTERVAL_MS))

  let data
  try {
    const res = await fetch('/plugin/mcp/cti/status')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    data = await res.json()
  } catch (e) {
    ctiStatus.value = `Lost contact with the server: ${e.message}`
    return
  }

  if (data.state === 'running') {
    loadRawFiles()
    return pollCtiStatus(attempt + 1)
  }

  if (data.state === 'failed') {
    ctiStatus.value = `Pipeline failed: ${data.error || 'no detail reported'}`
  } else {
    ctiStatus.value = 'Pipeline complete.'
  }

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

/* The whole row toggles its checkbox, so it has to read as clickable. */
.is-clickable-row {
  cursor: pointer;
}
.is-clickable-row:hover {
  background-color: rgba(158, 98, 255, 0.08);
}
/* The checkbox keeps its own cursor: clicking it does the same thing, but a
   text cursor over the label would suggest it does not. */
.is-clickable-row input[type="checkbox"] {
  cursor: pointer;
}
.dir-caret {
  display: inline-block;
  width: 1em;
  color: #9e62ff;
}

/* Both tables share these so the File column starts at the same x on each. */
.select-col {
  width: 2.5rem;
}
.view-col {
  width: 5rem;
}
.file-cell {
  word-break: break-all;
}

/* ============================================================
 * RAW REPORT PREVIEW
 * ============================================================ */
.raw-viewer {
  width: min(900px, 92vw);
}
.raw-viewer__heading {
  flex-grow: 1;
  min-width: 0;
}
.raw-viewer__meta {
  font-size: 0.75rem;
  color: #a0a0a0;
  margin-top: 0.15rem;
}
.raw-viewer__close {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: #9e62ff;
  font-size: 2rem;
  line-height: 1;
  padding: 0 0.25rem;
  transition: color 0.15s ease;
}
.raw-viewer__close:hover,
.raw-viewer__close:focus-visible {
  color: #c9a3ff;
}
/* pre would otherwise force the modal wider than the viewport on a report
   with long unbroken lines, which a PDF extraction often has. */
.raw-viewer__text {
  background: transparent;
  padding: 0;
  font-size: 0.8rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  color: #f5f5f5;
}

/* The box stretches to match the config panel beside it, so the dropzone
   takes the slack rather than leaving it under a fixed-height target. */
.cti-ingest {
  display: flex;
  flex-direction: column;
}

.cti-dropzone {
  border: 1px dashed rgba(158, 98, 255, 0.45);
  border-radius: 8px;
  background-color: #242424;
  padding: 1.75rem 1rem;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
  /* Grow into the leftover height, but keep a sane target when the column
     is short (narrow viewport, or the panel collapses under it). */
  flex-grow: 1;
  min-height: 7rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
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
  /* Spacing comes from the zone's gap now. */
  margin: 0;
  font-size: 0.75rem;
  color: #a0a0a0;
}

/* Pointer-events off so a drag over the filename does not fire dragleave on
   the zone, which would flicker the highlight. */
.cti-dropzone * {
  pointer-events: none;
}
</style>
