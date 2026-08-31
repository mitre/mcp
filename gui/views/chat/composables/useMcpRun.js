// One MCP run: POST /plugin/mcp/execute, then poll /plugin/mcp/status until
// FINISHED or FAILED. Returns reactive state plus start() and attach().
//
// Each run is independent. start() resets all state and begins fresh; the
// caller decides how to surface results (e.g. push into a chat transcript).
//
// The run itself belongs to the server: /execute hands back a run_id right
// away and the workflow keeps going no matter what the browser does. attach()
// is the counterpart to start() for a run that is already in flight, which is
// how a remounted view picks its run back up after the user navigated away.

import { ref, computed } from 'vue'

const POLL_INTERVAL_MS = 1000

// One failed status GET is usually a blip (CALDERA busy on the event loop it
// serves every plugin from), not a dead run. Only give up after this many in
// a row so a hiccup does not report a healthy run as FAILED.
const MAX_CONSECUTIVE_POLL_ERRORS = 3

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
  let consecutivePollErrors = 0
  // Set by stop() so a status GET that is already in flight cannot start a
  // fresh interval after the caller has walked away (unmount).
  let detached = false

  function _clearTimer() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function reset() {
    status.value = 'idle'
    stage.value = ''
    runId.value = null
    prompt.value = ''
    reasoning.value = ''
    finalResult.value = ''
    trajectory.value = {}
    errorMessage.value = ''
    consecutivePollErrors = 0
    detached = false
    _clearTimer()
  }

  /** Submit a new run and begin polling it; resolves with the /execute body. */
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

  /** Resume polling a run already in flight on the server, by its `run_id`. */
  async function attach(id) {
    reset()
    status.value = 'RUNNING'
    runId.value = id
    // Read the run once up front so a remounted view paints its real state
    // straight away instead of sitting on stale content for a whole interval.
    const stillLive = await _pollOnce(id)
    if (stillLive && !detached) _beginPolling(id)
  }

  function _applySnapshot(data) {
    status.value = data.status || 'unknown'
    stage.value = data.stage || ''
    prompt.value = data.prompt || prompt.value
    reasoning.value = data.reasoning || ''
    finalResult.value = data.process_result || ''
    trajectory.value = data.trajectory || {}
    // The backend writes a per-run `error` field into the run cache when
    // the workflow raises (see mcp_svc._run_execution's except branch).
    // Surface it so ChatMessage can render the actual cause under the
    // "Run failed." headline instead of leaving it blank.
    if (data.error) errorMessage.value = data.error
  }

  // True once this composable has moved on from `id`, which reset() signals by
  // clearing runId. "New chat" resets mid-run, so a GET issued for the run the
  // user just walked away from can still be in flight; letting it land would
  // strand the view on a RUNNING status nothing polls any more.
  function _superseded(id) {
    return runId.value !== id
  }

  // Pull one status snapshot into the reactive state. Returns false once
  // polling should stop, either because the run reached a terminal state or
  // because the endpoint will not answer for this run again.
  async function _pollOnce(id) {
    try {
      const res = await $api.get('/plugin/mcp/status', { params: { run_id: id } })
      if (_superseded(id)) return false
      consecutivePollErrors = 0
      _applySnapshot(res.data)
      return status.value !== 'FINISHED' && status.value !== 'FAILED'
    } catch (err) {
      if (_superseded(id)) return false
      // 404 means the run left the live cache: the server restarted, or the
      // run aged out of the LRU bound. Neither resolves by asking again.
      if (err?.response?.status === 404) {
        status.value = 'FAILED'
        errorMessage.value =
          'This run is no longer tracked live. '
          + 'Check the History tab for its result.'
        return false
      }
      consecutivePollErrors += 1
      if (consecutivePollErrors < MAX_CONSECUTIVE_POLL_ERRORS) return true
      status.value = 'FAILED'
      errorMessage.value = 'Polling failed.'
      return false
    }
  }

  function _beginPolling(id) {
    _clearTimer()
    // Scoped per polling session so a slow status GET cannot stack up behind
    // itself when the server takes longer than one interval to answer.
    let inFlight = false
    pollTimer = setInterval(async () => {
      if (inFlight) return
      inFlight = true
      try {
        const stillLive = await _pollOnce(id)
        if (!stillLive) _clearTimer()
      } finally {
        inFlight = false
      }
    }, POLL_INTERVAL_MS)
  }

  /** Stop polling without touching run state; the server run keeps going. */
  function stop() {
    detached = true
    _clearTimer()
  }

  return {
    status, stage, runId, prompt, reasoning, finalResult, trajectory,
    errorMessage, isRunning, isFinished, isFailed,
    start, attach, stop, reset,
  }
}
