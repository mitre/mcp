// Per-workflow chat session state, persisted to localStorage.
//
// Why this exists:
//   ChatWorkflow.vue mounts and unmounts whenever the user clicks Back
//   to the landing page and then re-enters a workflow card. All in-
//   component refs (messages, sessionId, composer text, attachedIntel,
//   historyEnabled) reset on each mount, so the user perceives a fresh
//   session every time. The backend already keys chat history by a
//   server-assigned session_id, so the only thing missing on the client
//   is durable storage for that id and the rendered transcript.
//
// What it owns:
//   For one (workflow_id), this composable owns four pieces of state:
//     - messages           the transcript shown in ChatTranscript
//     - sessionId          the server-assigned id paired with this
//                          conversation; null only for a brand-new chat
//     - historyEnabled     whether the next turn passes prior history
//                          to the LLM (only meaningful for opt-in
//                          workflows)
//     - attachedIntel      which CTI bundles are attached to
//                          the next prompt
//
// What it does not own:
//   composerText, transient run-state (status/stage/finalResult on the
//   in-flight assistant message). Composer text is intentionally not
//   persisted: half-typed prompts surviving a remount is a worse UX
//   than a clean text box. In-flight run state belongs to useMcpRun and
//   is reconstructed from the polling endpoint; localStorage only keeps
//   the run_id needed to ask for it again.
//
// Storage shape:
//   localStorage key 'mcp_chat_sessions' holds:
//     { schema: 1, workflows: { <workflow_id>: { messages, sessionId,
//                                                historyEnabled,
//                                                attachedIntel,
//                                                updated_at } } }
//   The schema version lets future changes drop incompatible blobs
//   without confusing rehydration.
//
// Assistant messages carry their run_id, so a bubble left mid-run survives
// a remount and ChatWorkflow re-attaches a poller to it. Older RUNNING
// messages, and any with no run_id, are failed on hydrate: nothing is going
// to move them again.
//
// Limits:
//   Per-workflow caps at MAX_MESSAGES messages and MAX_BYTES total
//   serialized size. Older messages are dropped first. localStorage
//   is typically 5–10 MB per origin; we stay well under that.
//
// Conversation archive (reopenable "Past chats"):
//   The live per-workflow slice above is only the CURRENT transcript. "New
//   chat" (reset()) and reopening an archived chat ARCHIVE the outgoing
//   transcript instead of destroying it, under a separate localStorage key
//   ('mcp_chat_conversations') keyed by a generated conversation id:
//     { schema, conversations: { <id>: { id, workflow_id, title, created_ts,
//                                         messages, sessionId } } }
//   A conversation is in ONE place at a time: the live slice or the archive
//   (reopen moves it back to live and archives whatever was live).
//
//   ENCRYPTED AT REST: the archive is stored as AES-GCM ciphertext under a
//   NON-EXTRACTABLE CryptoKey generated once and kept in IndexedDB, so the key
//   material is never readable from JS and the localStorage value is not a
//   plaintext transcript. When Web Crypto or IndexedDB is unavailable (private
//   window, insecure context, blocked storage) the archive is NOT persisted;
//   it never falls back to plaintext, and the live chat keeps working.
//
//   CAVEAT: this only keeps the blob unreadable at rest. It is not secret
//   from code running in the same origin (the key is usable, just not
//   exportable); real confidentiality would need server-side storage.

import { ref, watch } from 'vue'

const STORAGE_KEY = 'mcp_chat_sessions'
const SCHEMA_VERSION = 1
const MAX_MESSAGES = 200
const MAX_BYTES = 750_000  // ~750 KB per workflow keeps us safely under quota

// --- Conversation archive storage + at-rest encryption ----------------------
const CONVERSATIONS_KEY = 'mcp_chat_conversations'
const CONVERSATIONS_SCHEMA = 1
const MAX_CONVERSATIONS = 50            // oldest archived chats drop past this
const MAX_CONVERSATIONS_BYTES = 2_500_000  // defensive serialized-size budget
const IDB_NAME = 'mcp_chat_crypto'
const IDB_STORE = 'keys'
const IDB_KEY_ID = 'conversations-aes-gcm'

function _readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { schema: SCHEMA_VERSION, workflows: {} }
    const parsed = JSON.parse(raw)
    if (parsed?.schema !== SCHEMA_VERSION || !parsed.workflows) {
      // Schema mismatch: drop the old blob rather than risk hydrating
      // it into an incompatible component.
      return { schema: SCHEMA_VERSION, workflows: {} }
    }
    return parsed
  } catch (e) {
    console.warn('[MCP] Failed to read chat sessions:', e)
    return { schema: SCHEMA_VERSION, workflows: {} }
  }
}

function _writeAll(blob) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(blob))
  } catch (e) {
    console.warn('[MCP] Failed to persist chat sessions:', e)
  }
}

function _readWorkflow(workflowId) {
  const all = _readAll()
  return all.workflows[workflowId] || null
}

function _writeWorkflow(workflowId, slice) {
  const all = _readAll()
  all.workflows[workflowId] = { ...slice, updated_at: Date.now() }
  _writeAll(all)
}

function _trimMessages(messages) {
  // Cap by count first (cheap), then by serialized size (defensive).
  let trimmed = messages.length > MAX_MESSAGES
    ? messages.slice(messages.length - MAX_MESSAGES)
    : messages
  while (trimmed.length > 1 && JSON.stringify(trimmed).length > MAX_BYTES) {
    trimmed = trimmed.slice(1)
  }
  return trimmed
}

function _markUnresumableRunning(messages) {
  // Only the newest RUNNING message can be re-attached; the view polls one
  // run at a time. A bubble left frozen on "Thinking" would lie to the user.
  const resumableIndex = messages.reduce(
    (last, m, i) => (m.status === 'RUNNING' && m.runId ? i : last),
    -1
  )
  return messages.map((m, i) => {
    if (m.status !== 'RUNNING' || i === resumableIndex) return m
    return {
      ...m,
      status: 'FAILED',
      stage: '',
      errorMessage:
        m.errorMessage
        || 'The page stopped tracking this run. '
           + 'Check the History tab for the final result.',
    }
  })
}

// ----------------------------------------------------------------------------
// Shared crypto + archive-store helper
//
// One helper for the whole conversation archive: the AES-GCM key lifecycle,
// encrypt/decrypt, and the encrypted-localStorage read/write. Everything here
// is module-level (shared across every per-workflow composable instance) and
// returns null / an empty store on any failure - it never throws into the UI.
// ----------------------------------------------------------------------------

function _subtle() {
  try {
    return (typeof crypto !== 'undefined' && crypto && crypto.subtle) ? crypto.subtle : null
  } catch {
    return null
  }
}

function _idbOpen() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined' || !indexedDB) {
      reject(new Error('indexedDB unavailable'))
      return
    }
    let req
    try {
      req = indexedDB.open(IDB_NAME, 1)
    } catch (e) {
      reject(e)
      return
    }
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(IDB_STORE)) db.createObjectStore(IDB_STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error || new Error('indexedDB open error'))
  })
}

function _idbGet(db, key) {
  return new Promise((resolve, reject) => {
    const req = db.transaction(IDB_STORE, 'readonly').objectStore(IDB_STORE).get(key)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error || new Error('indexedDB get error'))
  })
}

function _idbPut(db, key, value) {
  return new Promise((resolve, reject) => {
    const req = db.transaction(IDB_STORE, 'readwrite').objectStore(IDB_STORE).put(value, key)
    req.onsuccess = () => resolve(true)
    req.onerror = () => reject(req.error || new Error('indexedDB put error'))
  })
}

// Resolve the encryption key once per page load. First use generates a
// non-extractable AES-GCM key and persists the CryptoKey object itself in
// IndexedDB (structured-cloneable even though non-extractable); later loads
// reuse it. Returns null (never throws) when Web Crypto / IndexedDB is
// unavailable so callers degrade to not-persisting.
let _cryptoKeyPromise = null
async function _getCryptoKey() {
  if (_cryptoKeyPromise) return _cryptoKeyPromise
  _cryptoKeyPromise = (async () => {
    const subtle = _subtle()
    if (!subtle) return null
    let db
    try {
      db = await _idbOpen()
    } catch (e) {
      console.warn('[MCP] conversation-history key store unavailable:', e)
      return null
    }
    try {
      let key = await _idbGet(db, IDB_KEY_ID)
      if (!key) {
        key = await subtle.generateKey(
          { name: 'AES-GCM', length: 256 },
          false,                      // non-extractable: material never leaves the browser
          ['encrypt', 'decrypt'],
        )
        await _idbPut(db, IDB_KEY_ID, key)
      }
      return key || null
    } catch (e) {
      console.warn('[MCP] conversation-history key init failed:', e)
      return null
    } finally {
      try { db.close() } catch { /* ignore */ }
    }
  })()
  return _cryptoKeyPromise
}

function _bytesToB64(bytes) {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  let bin = ''
  const CHUNK = 0x8000
  for (let i = 0; i < arr.length; i += CHUNK) {
    bin += String.fromCharCode.apply(null, arr.subarray(i, i + CHUNK))
  }
  return btoa(bin)
}

function _b64ToBytes(b64) {
  const bin = atob(b64)
  const arr = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
  return arr
}

// Encrypt an object into a base64 { v, iv, ct } envelope, or null when crypto
// is unavailable. Fresh 12-byte IV per write (AES-GCM requirement).
async function _encryptJSON(obj) {
  try {
    const key = await _getCryptoKey()
    const subtle = _subtle()
    if (!key || !subtle) return null
    const iv = crypto.getRandomValues(new Uint8Array(12))
    const plaintext = new TextEncoder().encode(JSON.stringify(obj))
    const ct = await subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext)
    return { v: 1, iv: _bytesToB64(iv), ct: _bytesToB64(new Uint8Array(ct)) }
  } catch (e) {
    console.warn('[MCP] conversation-history encrypt failed:', e)
    return null
  }
}

async function _decryptJSON(envelope) {
  try {
    const key = await _getCryptoKey()
    const subtle = _subtle()
    if (!key || !subtle || !envelope || !envelope.iv || !envelope.ct) return null
    const pt = await subtle.decrypt(
      { name: 'AES-GCM', iv: _b64ToBytes(envelope.iv) },
      key,
      _b64ToBytes(envelope.ct),
    )
    return JSON.parse(new TextDecoder().decode(pt))
  } catch (e) {
    console.warn('[MCP] conversation-history decrypt failed:', e)
    return null
  }
}

// Decrypt + parse the archive. Returns an empty store on anything unexpected
// (missing, tampered, wrong schema, crypto unavailable) so a bad blob can never
// wedge the feature.
async function _readConversations() {
  const empty = { schema: CONVERSATIONS_SCHEMA, conversations: {} }
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY)
    if (!raw) return empty
    const record = JSON.parse(raw)
    if (!record || !record.enc) return empty
    const decrypted = await _decryptJSON(record.enc)
    if (!decrypted || decrypted.schema !== CONVERSATIONS_SCHEMA ||
        !decrypted.conversations || typeof decrypted.conversations !== 'object') {
      return empty
    }
    return { schema: CONVERSATIONS_SCHEMA, conversations: decrypted.conversations }
  } catch (e) {
    console.warn('[MCP] Failed to read conversation archive:', e)
    return empty
  }
}

// Encrypt the whole archive and store only the ciphertext envelope. If crypto
// is unavailable we DO NOT fall back to plaintext - we skip persisting, so a
// transcript never lands on disk unencrypted. Returns true on success.
async function _writeConversations(store) {
  try {
    const enc = await _encryptJSON({
      schema: CONVERSATIONS_SCHEMA,
      conversations: store.conversations || {},
    })
    if (!enc) {
      console.warn('[MCP] conversation-history encryption unavailable; archive not persisted')
      return false
    }
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify({ schema: CONVERSATIONS_SCHEMA, enc }))
    return true
  } catch (e) {
    console.warn('[MCP] Failed to persist conversation archive:', e)
    return false
  }
}

function _newConvId() {
  return `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _deriveTitle(messages) {
  const firstUser = Array.isArray(messages)
    ? messages.find(m => m && m.role === 'user' && typeof m.text === 'string' && m.text.trim())
    : null
  const raw = (firstUser?.text || '').trim().replace(/\s+/g, ' ')
  if (!raw) return 'Untitled conversation'
  return raw.length > 60 ? `${raw.slice(0, 59)}…` : raw
}

function _capConversations(store) {
  // Drop the oldest archived conversations once we exceed the count budget,
  // then (defensively) the serialized-size budget.
  const byOldest = () => Object.values(store.conversations).sort(
    (a, b) => (a.created_ts || 0) - (b.created_ts || 0),
  )
  let entries = byOldest()
  if (entries.length > MAX_CONVERSATIONS) {
    for (const e of entries.slice(0, entries.length - MAX_CONVERSATIONS)) {
      delete store.conversations[e.id]
    }
  }
  while (Object.keys(store.conversations).length > 1 &&
         JSON.stringify(store.conversations).length > MAX_CONVERSATIONS_BYTES) {
    const oldest = byOldest()[0]
    if (!oldest) break
    delete store.conversations[oldest.id]
  }
}

// Mutate a given store object to add one archived conversation from a snapshot
// { messages, sessionId }. No-op (returns null) for an empty snapshot so we
// never archive a blank chat. Caller owns the subsequent _writeConversations.
function _putArchive(store, workflowId, snapshot) {
  if (!snapshot || !Array.isArray(snapshot.messages) || !snapshot.messages.length) return null
  const id = _newConvId()
  store.conversations[id] = {
    id,
    workflow_id: workflowId,
    title: _deriveTitle(snapshot.messages),
    created_ts: Date.now(),
    messages: snapshot.messages,
    sessionId: snapshot.sessionId ?? null,
  }
  _capConversations(store)
  return store.conversations[id] || null
}

// Read-modify-write convenience: archive one snapshot into the persisted store.
async function _archiveSlice(workflowId, snapshot) {
  const store = await _readConversations()
  const added = _putArchive(store, workflowId, snapshot)
  if (!added) return null
  const ok = await _writeConversations(store)
  return ok ? added : null
}

export function useChatSession(workflowId) {
  const messages = ref([])
  const sessionId = ref(null)
  const historyEnabled = ref(true)
  const attachedIntel = ref([])

  function hydrate() {
    const slice = _readWorkflow(workflowId)
    if (!slice) return
    messages.value = _markUnresumableRunning(slice.messages || [])
    sessionId.value = slice.sessionId ?? null
    historyEnabled.value =
      typeof slice.historyEnabled === 'boolean' ? slice.historyEnabled : true
    attachedIntel.value = Array.isArray(slice.attachedIntel) ? slice.attachedIntel : []
  }

  function persist() {
    _writeWorkflow(workflowId, {
      messages: _trimMessages(messages.value),
      sessionId: sessionId.value,
      historyEnabled: historyEnabled.value,
      attachedIntel: attachedIntel.value,
    })
  }

  // Persist on any change. deep:true catches in-place message mutation
  // (status, finalResult, errorMessage updates from useMcpRun's watcher).
  watch(
    [messages, sessionId, historyEnabled, attachedIntel],
    persist,
    { deep: true }
  )

  function reset() {
    // Explicit "New chat": wipe both memory and disk for this workflow, after
    // taking a snapshot so the transcript is ARCHIVED rather than lost. The
    // snapshot is frozen before the wipe so the async (encrypted) archive
    // write cannot race it. Returns the archive promise so a caller can
    // refresh a history list; archive errors never block New chat.
    const snapshot = {
      messages: messages.value.slice(),
      sessionId: sessionId.value,
    }
    messages.value = []
    sessionId.value = null
    historyEnabled.value = true
    attachedIntel.value = []
    const all = _readAll()
    delete all.workflows[workflowId]
    _writeAll(all)
    if (!snapshot.messages.length) return Promise.resolve(null)
    return _archiveSlice(workflowId, snapshot).catch(e => {
      console.warn('[MCP] Failed to archive conversation on New chat:', e)
      return null
    })
  }

  // --- Conversation archive API (drives the "Past chats" list) --------------
  // Metadata for this workflow's archived chats, newest first. No message
  // bodies; reopenConversation() loads the full transcript.
  async function listConversations() {
    try {
      const store = await _readConversations()
      return Object.values(store.conversations)
        .filter(c => c && c.workflow_id === workflowId)
        .sort((a, b) => (b.created_ts || 0) - (a.created_ts || 0))
        .map(c => ({
          id: c.id,
          workflow_id: c.workflow_id,
          title: c.title || 'Untitled conversation',
          created_ts: c.created_ts || 0,
          message_count: Array.isArray(c.messages) ? c.messages.length : 0,
        }))
    } catch (e) {
      console.warn('[MCP] Failed to list conversations:', e)
      return []
    }
  }

  // Reopen an archived chat as the live transcript. Removes the reopened entry
  // from the archive and archives whatever is live in its place (removing first,
  // so the archive cap never evicts an unrelated chat to make room), then
  // restores its messages and sessionId. Reopening is never destructive: if the
  // archive write fails, it returns false before the live chat is touched, and
  // both chats stay where they were. RUNNING bubbles get the same treatment as
  // on hydrate: only the newest one with a run_id stays RUNNING, for the view to
  // re-attach a poller to.
  async function reopenConversation(id) {
    try {
      const store = await _readConversations()
      const conv = store.conversations[id]
      if (!conv) return false
      delete store.conversations[id]
      _putArchive(store, workflowId, {
        messages: messages.value.slice(),
        sessionId: sessionId.value,
      })
      if (!await _writeConversations(store)) return false
      messages.value = _markUnresumableRunning(Array.isArray(conv.messages) ? conv.messages : [])
      sessionId.value = conv.sessionId ?? null
      historyEnabled.value = true
      attachedIntel.value = []
      persist()
      return true
    } catch (e) {
      console.warn('[MCP] Failed to reopen conversation:', e)
      return false
    }
  }

  async function deleteConversation(id) {
    try {
      const store = await _readConversations()
      if (!store.conversations[id]) return false
      delete store.conversations[id]
      await _writeConversations(store)
      return true
    } catch (e) {
      console.warn('[MCP] Failed to delete conversation:', e)
      return false
    }
  }

  // "Clear all" in the Past chats list: deletes THIS workflow's archived chats
  // only. The archive is shared by every workflow, so the others' entries are
  // written back (still encrypted) and the key is removed only once nothing is
  // left. An archive that cannot be decrypted reads as empty, so nothing is
  // removed or rewritten.
  async function clearConversations() {
    try {
      const store = await _readConversations()
      const ids = Object.keys(store.conversations)
        .filter(id => store.conversations[id]?.workflow_id === workflowId)
      if (!ids.length) return true
      for (const id of ids) delete store.conversations[id]
      if (!Object.keys(store.conversations).length) {
        localStorage.removeItem(CONVERSATIONS_KEY)
        return true
      }
      return await _writeConversations(store)
    } catch (e) {
      console.warn('[MCP] Failed to clear conversation archive:', e)
      return false
    }
  }

  return {
    messages,
    sessionId,
    historyEnabled,
    attachedIntel,
    hydrate,
    // For the one write that cannot wait for the watcher: a run_id arriving
    // after unmount, once the scope holding that watcher is stopped.
    persist,
    reset,
    // Conversation archive (encrypted at rest), consumed by ChatHistoryList.
    listConversations,
    reopenConversation,
    deleteConversation,
    clearConversations,
  }
}
