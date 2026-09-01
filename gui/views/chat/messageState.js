// One definition of "this assistant bubble carries an answer the user can
// read", shared by the transcript that renders it and the header that counts
// it. The two used to decide separately: the header allow-listed FINISHED
// while ChatMessage rendered a result for anything that was not RUNNING,
// FAILED or KILLED. A snapshot arriving without a status becomes 'unknown'
// (useMcpRun._applySnapshot), which showed an answer the header refused to
// count.

/**
 * Statuses an assistant bubble renders as something other than an answer.
 * ChatMessage carries one branch per member, each with its own styling.
 */
export const UNDELIVERED_STATUSES = new Set(['RUNNING', 'FAILED', 'KILLED'])

/** True when this message is an assistant answer, whatever its exact status. */
export function isDeliveredResponse(message) {
  // Missing role defaults to assistant, matching how ChatMessage decides
  // which bubble to draw. Disagreeing here is the bug this module exists
  // to prevent.
  return (
    (message?.role || 'assistant') === 'assistant'
    && !UNDELIVERED_STATUSES.has(message?.status)
  )
}
