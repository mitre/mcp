/* ============================================================
 * PLUGIN REQUESTS
 *
 * Caldera gates plugin routes per handler, and check_permissions answers an
 * expired session by raising HTTPFound('/login'). fetch follows that
 * redirect, so the reply arrives as a 200 carrying the login page: res.ok is
 * true, res.json() throws on the HTML, and the operator was left looking at
 * an empty table with nothing to explain it. Every caller goes through these
 * so no call site can forget the check.
 * ============================================================ */

export const SESSION_EXPIRED =
  'Session expired. Sign in to CALDERA again, then reload this page.'

function isLoginPage(res) {
  return res.redirected && new URL(res.url).pathname.startsWith('/login')
}

/**
 * Call a plugin endpoint and return the response.
 *
 * Rejects with a message written for the operator, so callers report
 * `e.message` rather than assembling their own.
 *
 * @param {string} what how to name the failure: "Could not load the list"
 */
export async function request(what, url, options) {
  let res
  try {
    res = await fetch(url, options)
  } catch (e) {
    throw new Error(`Could not reach the server: ${e.message}`)
  }

  // A non-default login handler answers 401/403 instead of redirecting.
  if (isLoginPage(res) || res.status === 401 || res.status === 403) {
    throw new Error(SESSION_EXPIRED)
  }

  if (!res.ok) {
    // The API states its own refusals in an "error" key; a 500 has none.
    let detail = ''
    try { detail = (await res.json()).error || '' } catch { /* non-JSON body */ }
    throw new Error(`${what} (${res.status})${detail ? ': ' + detail : ''}.`)
  }

  return res
}

/** As `request`, decoding the body that every endpoint but download returns. */
export async function requestJson(what, url, options) {
  const res = await request(what, url, options)
  try {
    return await res.json()
  } catch {
    throw new Error(`${what}: the server sent a reply this page cannot read.`)
  }
}
