// One MCP run: POST /plugin/mcp/execute, then poll /plugin/mcp/status until
// it reaches a terminal status. Returns reactive state plus start(),
// attach() and requestStop().
//
// The run belongs to the server, so it outlives the browser. attach() is the
// counterpart to start() for one already in flight, which is how a remounted
// view picks its run back up. requestStop() is the only call that ends the
// server-side run; stop() below just detaches this page from it.

import { ref, computed } from 'vue'
import { SESSION_EXPIRED } from '../../../composables/request.js'

const POLL_INTERVAL_MS = 1000

// Anything the server will not move again. KILLED is a run the user stopped,
// or one the boot sweep reconciled; polling it forever locks the page.
const TERMINAL_STATUSES = new Set(['FINISHED', 'FAILED', 'KILLED'])

// A single failed status GET is usually a blip, not a dead run.
const MAX_CONSECUTIVE_POLL_ERRORS = 3

export function useMcpRun($api) {
  const status = ref('idle')          // 'idle' | 'RUNNING' | 'FINISHED' | 'FAILED' | 'KILLED'
  const stage = ref('')
  const runId = ref(null)
  const prompt = ref('')
  const reasoning = ref('')
  const finalResult = ref('')
  const trajectory = ref({})
  const errorMessage = ref('')
  // Set from the moment Stop is pressed until the run reaches a terminal
  // status. Unwinding an agent loop takes a few seconds, and the server
  // still reports RUNNING throughout.
  const stopping = ref(false)

  const isRunning = computed(() => status.value === 'RUNNING')
  const isFinished = computed(() => status.value === 'FINISHED')
  const isFailed = computed(() => status.value === 'FAILED')
  const isStopping = computed(() => stopping.value && isRunning.value)

  let pollTimer = null
  let consecutivePollErrors = 0
  // Set by stop() so a request already in flight cannot start a fresh
  // interval after the caller unmounted.
  let detached = false
  // Bumped by reset(). runId cannot mark supersession on its own: it is null
  // for the whole /execute POST, which is the window "New chat" opens.
  let generation = 0
  // Stop pressed before the run had an id. That window is not small: /execute
  // mints the MLflow run before it answers, so a slow tracking server holds it
  // open for as long as its retries last, which is exactly when a user reaches
  // for Stop. start() sends the cancel once the id arrives.
  let stopPending = false

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
    stopping.value = false
    stopPending = false
    consecutivePollErrors = 0
    detached = false
    generation += 1
    _clearTimer()
  }

  /**
   * Submit a run; resolves with the /execute body, or null if "New chat"
   * superseded it mid-POST. An unmounted caller still gets the body so the
   * run_id can be persisted; only the polling is skipped.
   */
  async function start(payload) {
    reset()
    const gen = generation
    status.value = 'RUNNING'
    prompt.value = payload.text || ''

    try {
      const response = await $api.post('/plugin/mcp/execute', payload)
      if (gen !== generation) return null
      runId.value = response.data.run_id
      if (stopPending) {
        stopPending = false
        _sendCancel(runId.value)
      }
      if (!detached) _beginPolling(runId.value)
      // The caller needs fields above the per-run scope, like session_id.
      return response.data
    } catch (err) {
      if (gen !== generation) return null
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
    // Read once up front so a remounted view paints real state immediately
    // instead of holding stale content for a whole interval.
    const stillLive = await _pollOnce(id)
    if (stillLive && !detached) _beginPolling(id)
  }

  // An expired session lands here as a 200 carrying the login page, not a
  // snapshot (see gui/composables/request.js). Never persist that as a status.
  function _isSnapshot(data) {
    return !!data && typeof data === 'object' && typeof data.status === 'string'
  }

  function _applySnapshot(data) {
    status.value = data.status || 'unknown'
    stage.value = data.stage || ''
    prompt.value = data.prompt || prompt.value
    reasoning.value = data.reasoning || ''
    finalResult.value = data.process_result || ''
    trajectory.value = data.trajectory || {}
    // The run cache carries the workflow's own exception text; without this
    // ChatMessage renders "Run failed." with no cause.
    if (data.error) errorMessage.value = data.error
  }

  // reset() signals "moved on" by clearing runId, so a GET issued for the
  // abandoned run must not land on the state that replaced it.
  function _superseded(id) {
    return runId.value !== id
  }

  // Returns false once polling should stop: terminal state, or superseded.
  async function _pollOnce(id) {
    try {
      const res = await $api.get('/plugin/mcp/status', { params: { run_id: id } })
      if (_superseded(id)) return false
      if (!_isSnapshot(res.data)) {
        status.value = 'FAILED'
        errorMessage.value = SESSION_EXPIRED
        return false
      }
      consecutivePollErrors = 0
      _applySnapshot(res.data)
      return !TERMINAL_STATUSES.has(status.value)
    } catch (err) {
      if (_superseded(id)) return false
      // 404 means the run left the live cache: server restart, or LRU
      // eviction. Neither resolves by asking again.
      if (err?.response?.status === 404) {
        status.value = 'FAILED'
        errorMessage.value =
          'This run is no longer tracked live. '
          + 'Check the History tab for its result.'
        return false
      }
      consecutivePollErrors += 1
      if (consecutivePollErrors < MAX_CONSECUTIVE_POLL_ERRORS) return true
      // Losing the poll says nothing about the run, which is still going.
      status.value = 'FAILED'
      errorMessage.value =
        'Lost contact with the server while this run was in progress. '
        + 'Check the History tab for its result.'
      return false
    }
  }

  function _beginPolling(id) {
    _clearTimer()
    // Per polling session, so a slow GET cannot stack up behind itself.
    let inFlight = false
    const timer = setInterval(async () => {
      if (inFlight) return
      inFlight = true
      try {
        const stillLive = await _pollOnce(id)
        // Only ever clear our own timer: clearInterval cannot cancel a
        // callback already suspended, so a superseded run can land here
        // after a newer one installed its poller.
        if (!stillLive && pollTimer === timer) _clearTimer()
      } finally {
        inFlight = false
      }
    }, POLL_INTERVAL_MS)
    pollTimer = timer
  }

  async function _sendCancel(id) {
    const gen = generation
    try {
      await $api.post('/plugin/mcp/cancel', { run_id: id })
    } catch {
      // The run is still whatever it was; let the poller report it. Guarded
      // like every other post-await write here: a cancel that rejects only
      // after a newer run started would otherwise clear that run's badge
      // back to "Working" while its own stop is still in flight.
      if (gen === generation && runId.value === id) stopping.value = false
    }
  }

  /**
   * Ask the server to cancel this run. Usable for the whole life of the run,
   * including before /execute has answered with an id. Polling carries on: the
   * run reaches KILLED only once its workflow has unwound, which is what the
   * caller waits for. Pressing twice is a harmless no-op.
   */
  async function requestStop() {
    if (!isRunning.value) return
    stopping.value = true
    if (!runId.value) {
      stopPending = true
      return
    }
    await _sendCancel(runId.value)
  }

  /** Stop polling without touching run state; the server run keeps going. */
  function stop() {
    detached = true
    _clearTimer()
  }

  return {
    status, stage, runId, prompt, reasoning, finalResult, trajectory,
    errorMessage, isRunning, isFinished, isFailed, isStopping,
    start, attach, requestStop, stop, reset,
  }
}
