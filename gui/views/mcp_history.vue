<template>
  <div class="is-flex is-justify-content-center" style="width: 100%;">
    <div style="width: 95%; max-width: 1400px;">
      <div class="box">

        <!-- =====================================================
             HEADER
             ===================================================== -->
        <div class="is-flex is-align-items-center is-justify-content-space-between mb-4">
          <h2 class="title is-4 has-text-primary mb-0">Run History</h2>
          <button class="button is-light is-small" @click="$emit('back')">
            ← Back
          </button>
        </div>

        <!-- =====================================================
             RUN LIST VIEW
             ===================================================== -->
        <div v-if="!selectedRun">

          <!-- Search -->
          <div class="field">
            <div class="control has-icons-left">
              <input
                class="input"
                type="text"
                v-model="searchQuery"
                placeholder="Search by prompt, run ID, status, or stage..."
              />
              <span class="icon is-left">
                <i class="fas fa-search"></i>
              </span>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="isLoading" class="has-text-centered p-5">
            <p>Loading run history…</p>
          </div>

          <!-- Error -->
          <div v-if="errorMessage" class="notification is-danger">
            {{ errorMessage }}
          </div>

          <!-- Table -->
          <div v-if="!isLoading && !errorMessage" class="table-container">
            <table class="table is-fullwidth is-hoverable history-table">
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Status</th>
                  <th>Prompt</th>
                  <th>Stage</th>
                  <th>Model</th>
                  <th>Duration</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="filteredRuns.length === 0">
                  <td colspan="7" class="has-text-centered has-text-grey">
                    No runs found
                  </td>
                </tr>

                <tr
                  v-for="run in filteredRuns"
                  :key="run.run_id"
                  class="clickable-row"
                  @click="viewRunDetail(run.run_id)"
                >
                  <td>{{ formatDate(run.start_time) }}</td>
                  <td>
                    <span class="tag" :class="getStatusClass(run.status)">
                      {{ run.status }}
                    </span>
                  </td>
                  <td class="prompt-preview">
                    {{ run.prompt || 'No prompt' }}
                  </td>
                  <td>{{ run.stage || '-' }}</td>
                  <td>{{ run.model || '-' }}</td>
                  <td>{{ formatDuration(run.start_time, run.end_time) }}</td>
                  <td>
                    <button class="button is-small is-info">
                      View
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p
            v-if="!isLoading && !errorMessage && runs.length"
            class="has-text-centered has-text-grey mt-4"
          >
            Showing {{ runs.length }} of {{ totalRuns }} runs
          </p>
        </div>

        <!-- =====================================================
             RUN DETAIL VIEW
             ===================================================== -->
        <div v-if="selectedRun">

          <div class="is-flex is-justify-content-space-between is-align-items-center mb-4">
            <h3 class="title is-5 mb-0">Run Details</h3>
            <button class="button is-light is-small" @click="selectedRun = null">
              ← Back to List
            </button>
          </div>

          <div v-if="isLoadingDetail" class="has-text-centered p-5">
            <p>Loading run details…</p>
          </div>

          <div v-if="runDetail && !isLoadingDetail">

            <!-- Metadata -->
            <div class="box">
              <div class="columns is-multiline">
                <div class="column is-half"><strong>Run ID:</strong> {{ runDetail.run_id }}</div>
                <div class="column is-half">
                  <strong>Status:</strong>
                  <span class="tag ml-2" :class="getStatusClass(runDetail.status)">
                    {{ runDetail.status }}
                  </span>
                </div>
                <div class="column is-half"><strong>Started:</strong> {{ formatDate(runDetail.start_time) }}</div>
                <div class="column is-half"><strong>Ended:</strong> {{ formatDate(runDetail.end_time) }}</div>

                <div class="column is-full">
                  <strong>Prompt:</strong>
                  <div class="detail-text-box">
                    {{ runDetail.prompt || 'No prompt' }}
                  </div>
                </div>

                <div v-if="runDetail.process_result" class="column is-full">
                  <strong>Result:</strong>
                  <div class="detail-text-box">
                    {{ runDetail.process_result }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Chain of Thought -->
            <div v-if="thoughts.length" class="box">
              <h4 class="title is-5">Chain of Thought</h4>

              <div v-for="(thought, idx) in thoughts" :key="idx" class="thought-step">
                <p class="has-text-weight-semibold has-text-primary">
                  Step {{ idx + 1 }}
                </p>

                <div class="thought-box">{{ thought }}</div>

                <div v-if="toolForThought(idx)" class="tool-call-section">
                  <p class="tool-name">
                    <strong>Tool:</strong> {{ toolForThought(idx).name }}
                  </p>

                  <pre v-if="toolForThought(idx).args" class="tool-args">
{{ formatJSON(toolForThought(idx).args) }}
                  </pre>

                  <pre v-if="toolForThought(idx).observation" class="tool-result">
{{ formatJSON(toolForThought(idx).observation) }}
                  </pre>
                </div>
              </div>
            </div>

            <!-- Final Reasoning -->
            <div v-if="runDetail.reasoning" class="box">
              <h4 class="title is-5">Final Reasoning</h4>
              <pre class="reasoning-box">{{ runDetail.reasoning }}</pre>
            </div>

            <!-- Raw -->
            <div class="box">
              <div class="is-flex is-align-items-center is-clickable" @click="showRawData = !showRawData">
                <h4 class="title is-6 mb-0">Raw Data</h4>
                <span class="icon ml-2">
                  <i class="fas" :class="showRawData ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
                </span>
              </div>

              <pre v-if="showRawData" class="raw-data-box mt-3">
{{ JSON.stringify(runDetail, null, 2) }}
              </pre>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/* ============================================================
 * Imports
 * ============================================================ */
import { computed, inject, onMounted, ref } from 'vue'

/* ============================================================
 * Injected Services
 * ============================================================ */
const $api = inject('$api')

/* ============================================================
 * State (Alphabetical)
 * ============================================================ */
const errorMessage = ref('')
const isLoading = ref(false)
const isLoadingDetail = ref(false)
const runs = ref([])
const runDetail = ref(null)
const searchQuery = ref('')
const selectedRun = ref(null)
const showRawData = ref(false)
const totalRuns = ref(0)

/* ============================================================
 * Fetching
 * ============================================================ */
async function fetchRuns() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const res = await $api.get('/plugin/mcp/history', {
      params: { limit: 100, offset: 0 }
    })

    runs.value = res.data.runs || []
    totalRuns.value = res.data.total || 0
  } catch (err) {
    errorMessage.value = err?.response?.data?.error || 'Failed to load run history.'
  } finally {
    isLoading.value = false
  }
}

async function viewRunDetail(runId) {
  selectedRun.value = runId
  isLoadingDetail.value = true
  showRawData.value = false

  try {
    const res = await $api.get('/plugin/mcp/history', {
      params: { run_id: runId }
    })
    runDetail.value = res.data
  } catch (err) {
    errorMessage.value = err?.response?.data?.error || 'Failed to load run details.'
  } finally {
    isLoadingDetail.value = false
  }
}

/* ============================================================
 * Computed
 * ============================================================ */
const filteredRuns = computed(() => {
  if (!searchQuery.value) return runs.value
  const q = searchQuery.value.toLowerCase()

  return runs.value.filter(r =>
    r.prompt?.toLowerCase().includes(q) ||
    r.run_id?.toLowerCase().includes(q) ||
    r.status?.toLowerCase().includes(q) ||
    r.stage?.toLowerCase().includes(q)
  )
})

const thoughts = computed(() => {
  const traj = runDetail.value?.trajectory
  if (!traj) return []

  return Object.entries(traj)
    .filter(([k]) => k.startsWith('thought_'))
    .sort(([a], [b]) => Number(a.match(/\d+/)) - Number(b.match(/\d+/)))
    .map(([, v]) => v)
})

/* ============================================================
 * Helpers
 * ============================================================ */
function toolForThought(idx) {
  const t = runDetail.value?.trajectory
  if (!t) return null

  const name = t[`tool_name_${idx}`]
  if (!name) return null

  return {
    name,
    args: t[`tool_args_${idx}`],
    observation: t[`observation_${idx}`]
  }
}

function formatJSON(val) {
  try {
    return JSON.stringify(typeof val === 'string' ? JSON.parse(val) : val, null, 2)
  } catch {
    return val
  }
}

function formatDate(ts) {
  return ts ? new Date(ts).toLocaleString() : '-'
}

function formatDuration(start, end) {
  if (!start) return '-'
  if (!end) return 'Running…'

  const sec = Math.floor((end - start) / 1000)
  const min = Math.floor(sec / 60)
  const hr = Math.floor(min / 60)

  return hr
    ? `${hr}h ${min % 60}m`
    : min
      ? `${min}m ${sec % 60}s`
      : `${sec}s`
}

function getStatusClass(status) {
  return {
    FINISHED: 'is-success',
    RUNNING: 'is-info',
    FAILED: 'is-danger'
  }[status] || 'is-light'
}

/* ============================================================
 * Lifecycle
 * ============================================================ */
onMounted(fetchRuns)
</script>
