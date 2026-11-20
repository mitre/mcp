"""Behaviour of the "Past chats" archive in gui/views/chat/composables/useChatSession.js.

The plugin has no JavaScript test runner, so these tests run the real composable
under Node: an in-memory localStorage and IndexedDB, Node's own Web Crypto, and a
two-line stand-in for vue's ref/watch. They skip when node is not on PATH.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

COMPOSABLE = (Path(__file__).resolve().parents[1]
              / "gui" / "views" / "chat" / "composables" / "useChatSession.js")
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_VUE_IMPORT = "from 'vue'"
_VUE_STUB = "export const ref = (value) => ({ value })\nexport const watch = () => {}\n"

# Shared by every scenario: in-memory localStorage (whose archive writes can be
# made to fail, as a full quota does) and IndexedDB, then the composable itself.
_PRELUDE = r"""
const kv = new Map()
const ARCHIVE_KEY = 'mcp_chat_conversations'
let failArchiveWrites = false
globalThis.localStorage = {
  getItem: k => (kv.has(k) ? kv.get(k) : null),
  setItem: (k, v) => {
    if (failArchiveWrites && k === ARCHIVE_KEY) {
      throw Object.assign(new Error('quota exceeded'), { name: 'QuotaExceededError' })
    }
    kv.set(k, String(v))
  },
  removeItem: k => { kv.delete(k) },
}
const keys = new Map()
const request = fn => {
  const r = {}
  queueMicrotask(() => {
    try { r.result = fn(); if (r.onsuccess) r.onsuccess() } catch (e) { r.error = e; if (r.onerror) r.onerror() }
  })
  return r
}
const db = {
  objectStoreNames: { contains: () => true },
  createObjectStore() {},
  close() {},
  transaction: () => ({ objectStore: () => ({
    get: k => request(() => keys.get(k)),
    put: (v, k) => request(() => { keys.set(k, v); return true }),
  }) }),
}
globalThis.indexedDB = {
  open: () => {
    const r = {}
    queueMicrotask(() => { r.result = db; if (r.onsuccess) r.onsuccess() })
    return r
  },
}
if (!globalThis.crypto || !globalThis.crypto.subtle) {
  globalThis.crypto = (await import('node:crypto')).webcrypto
}
const { useChatSession } = await import('./useChatSession.mjs')
const say = (s, text) => { s.messages.value = [{ id: `u-${text}`, role: 'user', text }] }
"""

# Three chats are archived for two workflows, then "Clear all" runs in one of them.
_CLEAR_ALL = r"""
const MARKERS = ['AUTHOR-MARKER', 'PLAN-MARKER']
const plaintext = () => MARKERS.some(m => (localStorage.getItem(ARCHIVE_KEY) || '').includes(m))

async function archive(workflow, text) {
  const s = useChatSession(workflow)
  s.messages.value = [{ id: 'u1', role: 'user', text }]
  s.sessionId.value = `sess-${workflow}`
  await s.reset()
  return s
}
const counts = async () => ({
  author: (await author.listConversations()).length,
  plan: (await plan.listConversations()).length,
})

const author = await archive('author', 'AUTHOR-MARKER first chat')
await archive('author', 'AUTHOR-MARKER second chat')
const plan = await archive('plan_execute', 'PLAN-MARKER chat')
const out = { before: await counts(), plaintext_before: plaintext() }
out.cleared = await author.clearConversations()
out.after = await counts()
out.plan_titles = (await plan.listConversations()).map(c => c.title)
out.stored_after_clear = localStorage.getItem(ARCHIVE_KEY) !== null
out.plaintext_after = plaintext()
out.cleared_last = await plan.clearConversations()
out.stored_after_last_clear = localStorage.getItem(ARCHIVE_KEY) !== null
console.log(JSON.stringify(out))
"""

# Chat A is archived and chat B is open when reopening A hits a full quota.
_REOPEN_WRITE_FAILS = r"""
const s = useChatSession('author')
say(s, 'chat A')
s.sessionId.value = 'sess-A'
await s.reset()
say(s, 'chat B')
s.sessionId.value = 'sess-B'
const [a] = await s.listConversations()
failArchiveWrites = true
const out = { reopened: await s.reopenConversation(a.id) }
failArchiveWrites = false
out.live = s.messages.value.map(m => m.text)
out.session = s.sessionId.value
out.archived = (await s.listConversations()).map(c => c.title)
console.log(JSON.stringify(out))
"""

# The archive is full (50 chats) when a chat in the middle is reopened.
_REOPEN_AT_CAP = r"""
let now = 1_000_000
Date.now = () => (now += 1000)
const s = useChatSession('plan_execute')
for (let i = 0; i < 50; i++) { say(s, `chat ${i}`); await s.reset() }
const before = await s.listConversations()
say(s, 'chat live')
const out = { before: before.length,
              reopened: await s.reopenConversation(before.find(c => c.title === 'chat 25').id) }
const titles = (await s.listConversations()).map(c => c.title)
out.after = titles.length
out.has = Object.fromEntries(['chat 0', 'chat 25', 'chat live'].map(t => [t, titles.includes(t)]))
console.log(JSON.stringify(out))
"""


def _run(tmp_path_factory, scenario):
    """Run one scenario against the real composable under Node; return its JSON result."""
    source = COMPOSABLE.read_text(encoding="utf-8")
    assert source.count(_VUE_IMPORT) == 1, "useChatSession.js no longer imports vue in one place"
    work = tmp_path_factory.mktemp("chat_archive")
    (work / "vue.mjs").write_text(_VUE_STUB, encoding="utf-8")
    (work / "useChatSession.mjs").write_text(
        source.replace(_VUE_IMPORT, "from './vue.mjs'"), encoding="utf-8")
    (work / "harness.mjs").write_text(_PRELUDE + scenario, encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(work / "harness.mjs")], cwd=work,
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def archive_run(tmp_path_factory):
    return _run(tmp_path_factory, _CLEAR_ALL)


def test_clear_all_removes_only_this_workflows_chats(archive_run):
    assert archive_run["before"] == {"author": 2, "plan": 1}
    assert archive_run["cleared"] is True
    assert archive_run["after"] == {"author": 0, "plan": 1}
    assert archive_run["plan_titles"] == ["PLAN-MARKER chat"]
    assert archive_run["stored_after_clear"] is True


def test_clearing_the_last_workflow_removes_the_archive(archive_run):
    assert archive_run["cleared_last"] is True
    assert archive_run["stored_after_last_clear"] is False


def test_the_archive_is_never_stored_in_plaintext(archive_run):
    assert archive_run["plaintext_before"] is False
    assert archive_run["plaintext_after"] is False


def test_reopen_keeps_the_open_chat_when_the_archive_write_fails(tmp_path_factory):
    run = _run(tmp_path_factory, _REOPEN_WRITE_FAILS)
    assert run["reopened"] is False
    assert run["live"] == ["chat B"]
    assert run["session"] == "sess-B"
    assert run["archived"] == ["chat A"]


def test_reopen_at_the_cap_evicts_no_other_chat(tmp_path_factory):
    run = _run(tmp_path_factory, _REOPEN_AT_CAP)
    assert run["before"] == 50
    assert run["reopened"] is True
    assert run["after"] == 50
    assert run["has"] == {"chat 0": True, "chat 25": False, "chat live": True}
