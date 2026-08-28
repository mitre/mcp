<template>
  <div class="is-flex is-justify-content-center" style="width: 100%;">
    <div style="width: 95%; max-width: 1400px;">
      <div class="box">
        <div class="is-flex is-align-items-center is-justify-content-space-between mb-4">
          <h2 class="title is-4 has-text-primary mb-0">Run History</h2>
          <button class="button is-light is-small" @click="$emit('back')">
            ← Back
          </button>
        </div>

        <div v-if="!selectedRun">
          <!-- Search and Filter Controls -->
          <div class="field">
            <div class="control has-icons-left">
              <input
                class="input"
                type="text"
                v-model="searchQuery"
                placeholder="Search by prompt, run ID, or status..."
              />
              <span class="icon is-left">
                <i class="fas fa-search"></i>
              </span>
            </div>
          </div>

          <!-- Loading State -->
          <div v-if="isLoading" class="has-text-centered p-5">
            <p>Loading run history...</p>
          </div>

          <!-- Error State -->
          <div v-if="errorMessage" class="notification is-danger">
            {{ errorMessage }}
          </div>

          <!-- Runs Table -->
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
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="filteredRuns.length === 0">
                  <td colspan="7" class="has-text-centered has-text-grey">
                    No runs found
                  </td>
                </tr>
                <tr v-for="run in filteredRuns" :key="run.run_id" class="clickable-row">
                  <td @click="viewRunDetail(run.run_id)">{{ formatDate(run.start_time) }}</td>
                  <td @click="viewRunDetail(run.run_id)">
                    <span class="tag" :class="getStatusClass(run.status)">
                      {{ run.status }}
                    </span>
                  </td>
                  <td @click="viewRunDetail(run.run_id)">
                    <div class="prompt-preview">
                      {{ run.prompt || 'No prompt' }}
                    </div>
                  </td>
                  <td @click="viewRunDetail(run.run_id)">{{ run.stage || '-' }}</td>
                  <td @click="viewRunDetail(run.run_id)">{{ run.model || '-' }}</td>
                  <td @click="viewRunDetail(run.run_id)">{{ formatDuration(run) }}</td>
                  <td>
                    <button class="button is-small is-info" @click="viewRunDetail(run.run_id)">
                      View Details
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination Info -->
          <div v-if="!isLoading && !errorMessage && runs.length > 0" class="has-text-centered mt-4">
            <p class="has-text-grey">Showing {{ runs.length }} of {{ totalRuns }} runs</p>
          </div>
        </div>

        <!-- Run Detail View -->
        <div v-if="selectedRun">
          <div class="is-flex is-justify-content-space-between is-align-items-center mb-4">
            <h3 class="title is-5 mb-0">Run Details</h3>
            <button class="button is-light is-small" @click="selectedRun = null">
              ← Back to List
            </button>
          </div>

          <div v-if="isLoadingDetail" class="has-text-centered p-5">
            <p>Loading run details...</p>
          </div>

          <div v-if="runDetail && !isLoadingDetail">
            <!-- Basic Info -->
            <div class="box">
              <div class="columns is-multiline">
                <div class="column is-half">
                  <p><strong>Run ID:</strong> {{ runDetail.run_id }}</p>
                </div>
                <div class="column is-half">
                  <p><strong>Status:</strong>
                    <span class="tag" :class="getStatusClass(runDetail.status)">
                      {{ runDetail.status }}
                    </span>
                  </p>
                </div>
                <div class="column is-half">
                  <p><strong>Started:</strong> {{ formatDate(runDetail.start_time) }}</p>
                </div>
                <div class="column is-half">
                  <p><strong>Ended:</strong> {{ formatDate(runDetail.end_time) }}</p>
                </div>
                <div class="column is-full">
                  <p><strong>Prompt:</strong></p>
                  <div class="detail-text-box">
                    {{ runDetail.prompt || 'No prompt' }}
                  </div>
                </div>
                <div class="column is-full" v-if="runDetail.process_result">
                  <p><strong>Result:</strong></p>
                  <div class="detail-text-box">
                    {{ runDetail.process_result }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Chain of Thought / Trajectory -->
            <div class="box" v-if="thoughts.length > 0">
              <h4 class="title is-5">Chain of Thought</h4>
              <div class="content">
                <div v-for="(thought, idx) in thoughts" :key="idx" class="thought-step">
                  <p class="has-text-weight-semibold has-text-primary">Step {{ idx + 1 }}:</p>
                  <div class="thought-box">
                    {{ thought }}
                  </div>

                  <!-- Show corresponding tool call if exists -->
                  <div v-if="getToolForThought(idx)" class="tool-call-section">
                    <p class="tool-name">
                      <strong>Tool:</strong> {{ getToolForThought(idx).name }}
                    </p>
                    <p class="tool-args" v-if="getToolForThought(idx).args">
                      <strong>Args:</strong> <code>{{ formatToolArgs(getToolForThought(idx).args) }}</code>
                    </p>
                    <div v-if="getToolForThought(idx).observation" class="tool-result">
                      <strong>Result:</strong> {{ formatObservation(getToolForThought(idx).observation) }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Reasoning -->
            <div class="box" v-if="runDetail.reasoning">
              <h4 class="title is-5">Final Reasoning</h4>
              <pre class="reasoning-box">{{ runDetail.reasoning }}</pre>
            </div>

            <!-- Raw Data (Collapsed by Default) -->
            <div class="box">
              <div class="is-flex is-align-items-center is-clickable" @click="showRawData = !showRawData">
                <h4 class="title is-6 mb-0">Raw Data</h4>
                <span class="icon ml-2">
                  <i class="fas" :class="showRawData ? 'fa-chevron-up' : 'fa-chevron-down'"></i>
                </span>
              </div>
              <div v-if="showRawData" class="mt-3">
                <pre class="raw-data-box">{{ JSON.stringify(runDetail, null, 2) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, ref, computed, onMounted } from "vue"

const $api = inject("$api")

const runs = ref([])
const totalRuns = ref(0)
const isLoading = ref(false)
const errorMessage = ref('')
const searchQuery = ref('')

const selectedRun = ref(null)
const runDetail = ref(null)
const isLoadingDetail = ref(false)
const showRawData = ref(false)

async function fetchRuns() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const res = await $api.get('/plugin/mcp/history/runs', {
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
    const res = await $api.get('/plugin/mcp/history/run', {
      params: { run_id: runId }
    })
    runDetail.value = res.data
  } catch (err) {
    errorMessage.value = err?.response?.data?.error || 'Failed to load run details.'
  } finally {
    isLoadingDetail.value = false
  }
}

const filteredRuns = computed(() => {
  if (!searchQuery.value) return runs.value

  const query = searchQuery.value.toLowerCase()
  return runs.value.filter(run => {
    return (
      run.prompt?.toLowerCase().includes(query) ||
      run.run_id?.toLowerCase().includes(query) ||
      run.status?.toLowerCase().includes(query) ||
      run.stage?.toLowerCase().includes(query)
    )
  })
})

const thoughts = computed(() => {
  if (!runDetail.value?.trajectory) return []

  const traj = runDetail.value.trajectory
  return Object.entries(traj)
    .filter(([key]) => key.startsWith("thought_"))
    .sort(([a], [b]) => {
      const getIndex = (k) => parseInt(k.match(/\d+/)?.[0] || 0)
      return getIndex(a) - getIndex(b)
    })
    .map(([_, val]) => val)
})

function getToolForThought(idx) {
  if (!runDetail.value?.trajectory) return null

  const traj = runDetail.value.trajectory
  const toolName = traj[`tool_name_${idx}`]
  const toolArgs = traj[`tool_args_${idx}`]
  const observation = traj[`observation_${idx}`]

  if (!toolName) return null

  return {
    name: toolName,
    args: toolArgs,
    observation: observation
  }
}

function formatToolArgs(args) {
  if (!args) return ''
  try {
    const parsed = typeof args === 'string' ? JSON.parse(args) : args
    return JSON.stringify(parsed, null, 2)
  } catch {
    return args
  }
}

function formatObservation(obs) {
  if (!obs) return ''
  try {
    const parsed = typeof obs === 'string' ? JSON.parse(obs) : obs
    if (typeof parsed === 'object') {
      return JSON.stringify(parsed, null, 2)
    }
    return obs
  } catch {
    return obs
  }
}

function formatDate(timestamp) {
  if (!timestamp) return '-'
  try {
    // MLflow timestamps are in milliseconds
    const date = new Date(timestamp)
    return date.toLocaleString()
  } catch {
    return '-'
  }
}

function formatDuration(run) {
  const { start_time: startTime, end_time: endTime, status } = run
  if (!startTime) return '-'
  if (!endTime) return 'Running...'
  // A run reconciled at boot was terminated by the sweep, not by itself,
  // so its end_time says when we noticed rather than when it stopped.
  if (status?.toUpperCase() === 'KILLED') return '-'

  try {
    const duration = endTime - startTime
    const seconds = Math.floor(duration / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`
    } else {
      return `${seconds}s`
    }
  } catch {
    return '-'
  }
}

function getStatusClass(status) {
  switch (status?.toUpperCase()) {
    case 'FINISHED':
      return 'is-success'
    case 'RUNNING':
      return 'is-info'
    case 'FAILED':
      return 'is-danger'
    case 'KILLED':
      return 'is-warning'
    default:
      return 'is-light'
  }
}

onMounted(() => {
  fetchRuns()
})
</script>

<style scoped>
/* Table Styling */
.table-container {
  overflow-x: auto;
}

.history-table {
  background-color: transparent;
}

.history-table thead {
  background-color: #7a00cc;
  color: white;
}

.history-table thead th {
  color: white !important;
  border-color: #6200a8 !important;
  font-weight: 600;
}

.history-table tbody tr.clickable-row {
  cursor: pointer;
  transition: background-color 0.2s ease;
  background-color: white;
}

.history-table tbody tr.clickable-row td {
  color: #363636 !important;
  border-color: #e0e0e0 !important;
}

.history-table tbody tr.clickable-row:nth-child(even) {
  background-color: #f5f5f5;
}

.history-table tbody tr.clickable-row:hover {
  background-color: #f0e6ff !important;
}

.prompt-preview {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Detail View Boxes */
.detail-text-box {
  background-color: #f9f9f9;
  border: 1px solid #e0e0e0;
  border-left: 4px solid #7a00cc;
  padding: 0.75rem;
  border-radius: 4px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: #363636;
}

/* Chain of Thought Styling */
.thought-step {
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e0e0e0;
}

.thought-step:last-child {
  border-bottom: none;
}

.thought-box {
  background-color: #f9f9f9;
  border: 1px solid #e0e0e0;
  border-left: 4px solid #7a00cc;
  padding: 1rem;
  margin-left: 1rem;
  margin-top: 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
  line-height: 1.6;
  color: #363636;
}

.tool-call-section {
  margin-left: 2rem;
  margin-top: 1rem;
  padding: 0.75rem;
  background-color: #f5f5ff;
  border-radius: 4px;
  border: 1px solid #d0d0ff;
}

.tool-name {
  font-size: 0.875rem;
  color: #3273dc;
  margin-bottom: 0.5rem;
}

.tool-args {
  font-size: 0.875rem;
  color: #666;
  margin-bottom: 0.5rem;
}

.tool-result {
  background-color: #fffef0;
  border: 1px solid #e8e6a0;
  padding: 0.75rem;
  margin-top: 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: #363636;
}

/* Reasoning Box */
.reasoning-box {
  background-color: #f9f9f9;
  border: 1px solid #e0e0e0;
  padding: 1rem;
  border-radius: 4px;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.875rem;
  line-height: 1.6;
  color: #363636;
  max-height: 400px;
  overflow: auto;
}

/* Raw Data Box */
.raw-data-box {
  background-color: #2b2b2b;
  color: #f8f8f2;
  padding: 1rem;
  border-radius: 4px;
  overflow: auto;
  max-height: 400px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.75rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* Code Styling */
code {
  background-color: #e8e8e8;
  color: #363636;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.85em;
}

/* General Pre Styling */
pre {
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>
