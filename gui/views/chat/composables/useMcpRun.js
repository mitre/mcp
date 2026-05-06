// One MCP run: POST /plugin/mcp/execute, then poll /plugin/mcp/status until
// FINISHED or FAILED. Returns reactive state plus a start() function.
//
// Each run is independent — start() resets all state and begins fresh. The
// caller decides how to surface results (e.g. push into a chat transcript).

import { ref, computed } from 'vue'

const POLL_INTERVAL_MS = 1000

export function useMcpRun($api) {
  const status = ref('idle')          // 'idle' | 'RUNNING' | 'FINISHED' | 'FAILED'
  const stage = ref('')
  const runId = ref(null)
  const prompt = ref('')
  const reasoning = ref('')
  const finalResult = ref('')
  const trajectory = ref({})
  const errorMessage = ref('')

  const isRunning = computed(() => status.value === 'RUNNING')
  const isFinished = computed(() => status.value === 'FINISHED')
  const isFailed = computed(() => status.value === 'FAILED')

  let pollTimer = null

  function reset() {
    status.value = 'idle'
    stage.value = ''
    runId.value = null
    prompt.value = ''
    reasoning.value = ''
    finalResult.value = ''
    trajectory.value = {}
    errorMessage.value = ''
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function start(payload) {
    reset()
    status.value = 'RUNNING'
    prompt.value = payload.text || ''

    try {
      const response = await $api.post('/plugin/mcp/execute', payload)
      runId.value = response.data.run_id
      _beginPolling(runId.value)
      // Hand the parsed response back so the caller can grab fields like
      // session_id that live above the per-run scope.
      return response.data
    } catch (err) {
      status.value = 'FAILED'
      errorMessage.value = err?.response?.data?.error || 'Submission failed.'
      throw err
    }
  }

  function _beginPolling(id) {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(async () => {
      try {
        const res = await $api.get('/plugin/mcp/status', { params: { run_id: id } })
        status.value = res.data.status || 'unknown'
        stage.value = res.data.stage || ''
        prompt.value = res.data.prompt || prompt.value
        reasoning.value = res.data.reasoning || ''
        finalResult.value = res.data.process_result || ''
        trajectory.value = res.data.trajectory || {}

        if (status.value === 'FINISHED' || status.value === 'FAILED') {
          clearInterval(pollTimer)
          pollTimer = null
        }
      } catch (e) {
        clearInterval(pollTimer)
        pollTimer = null
        status.value = 'FAILED'
        errorMessage.value = 'Polling failed.'
      }
    }, POLL_INTERVAL_MS)
  }

  function stop() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    status, stage, runId, prompt, reasoning, finalResult, trajectory,
    errorMessage, isRunning, isFinished, isFailed,
    start, stop, reset,
  }
}
