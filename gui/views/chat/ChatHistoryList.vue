<!--
  "Past chats" dropdown for a single MCP workflow. Lists the conversations that
  useChatSession archived when the user clicked "New chat" (or reopened another
  chat), newest first, and lets them reopen one, delete one, or clear all of
  this workflow's archived chats (other workflows' chats are kept).

  This component is only the read/reopen/delete UI. The archive itself (and its
  at-rest AES-GCM encryption) lives in useChatSession; the four async functions
  it needs are passed in as props, so there is a single storage/crypto layer,
  not a parallel one here.

  Caldera-native styling only: flat #222 / #191919 surfaces, #333 hairline
  borders, #8b00ff hover accent - no chat bubbles, no gradients.
-->
<template>
  <div ref="wrapRef" class="history-wrap">
    <button
      type="button"
      class="header-action"
      :class="{ 'is-open': open }"
      @click="toggle"
      title="Browse and reopen past conversations for this workflow"
    >
      <font-awesome-icon :icon="historyIcon" />
      <span>Past chats</span>
      <span v-if="count" class="log-count">{{ count }}</span>
    </button>

    <div v-if="open" class="history-panel">
      <div class="panel-head">
        <span class="panel-title">Past chats</span>
        <div class="panel-head-actions">
          <button
            v-if="items.length"
            type="button"
            class="panel-link"
            :class="{ 'is-confirming': confirmingClear }"
            @click="confirmingClear ? doClear() : (confirmingClear = true)"
            :title="confirmingClear ? 'Click again to confirm' : 'Delete every archived conversation of this workflow'"
          >{{ confirmingClear ? 'Confirm clear' : 'Clear all' }}</button>
          <button type="button" class="panel-close" @click="close" aria-label="Close">
            <font-awesome-icon :icon="closeIcon" />
          </button>
        </div>
      </div>

      <div class="panel-body">
        <p v-if="loading" class="panel-empty">Loading…</p>
        <p v-else-if="!items.length" class="panel-empty">
          No past conversations yet. Starting a New chat archives the current one here.
        </p>
        <ul v-else class="conv-list">
          <li v-for="c in items" :key="c.id" class="conv-row">
            <button
              type="button"
              class="conv-main"
              :disabled="disabled"
              :title="disabled
                ? 'Finish the current run before reopening a conversation'
                : 'Reopen this conversation'"
              @click="reopen(c.id)"
            >
              <span class="conv-title">{{ c.title }}</span>
              <span class="conv-meta">
                {{ formatTs(c.created_ts) }} · {{ c.message_count }} msg{{ c.message_count === 1 ? '' : 's' }}
              </span>
            </button>
            <button
              type="button"
              class="conv-del"
              title="Delete this conversation"
              @click.stop="remove(c.id)"
            >
              <font-awesome-icon :icon="trashIcon" />
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
// Import the icon objects directly and pass them to :icon - the magma SPA only
// runs its own main.js, so a plugin-local library.add would be dead code; the
// imported component + object bypass the global library lookup (same pattern as
// ChatComposer.vue and ChatWorkflow.vue).
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { faClockRotateLeft, faTrash, faXmark } from '@fortawesome/free-solid-svg-icons'

const props = defineProps({
  // Async archive API from useChatSession (single shared storage/crypto layer).
  listConversations: { type: Function, required: true },
  reopenConversation: { type: Function, required: true },
  deleteConversation: { type: Function, required: true },
  clearConversations: { type: Function, required: true },
  // Bump to force a reload (e.g. after New chat archives a transcript).
  refreshKey: { type: Number, default: 0 },
  // True while a run is in progress - reopening is blocked so we never swap the
  // transcript out from under a live run.
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['reopened'])

const historyIcon = faClockRotateLeft
const trashIcon = faTrash
const closeIcon = faXmark

const open = ref(false)
const loading = ref(false)
const items = ref([])
const confirmingClear = ref(false)
const wrapRef = ref(null)

// Count badge stays current even when the dropdown is closed (seeded onMounted
// and refreshed on refreshKey / after mutations).
const count = computed(() => items.value.length)

async function load() {
  loading.value = true
  try {
    const list = await props.listConversations()
    items.value = Array.isArray(list) ? list : []
  } catch (e) {
    console.warn('[MCP] Failed to load past conversations:', e)
    items.value = []
  } finally {
    loading.value = false
  }
}

function toggle() {
  open.value = !open.value
  if (open.value) {
    confirmingClear.value = false
    load()
  }
}

function close() {
  open.value = false
  confirmingClear.value = false
}

async function reopen(id) {
  if (props.disabled) return
  const ok = await props.reopenConversation(id)
  if (ok) {
    emit('reopened', id)
    close()
  } else {
    load()
  }
}

async function remove(id) {
  await props.deleteConversation(id)
  await load()
}

async function doClear() {
  confirmingClear.value = false
  await props.clearConversations()
  await load()
}

// Reload whenever the parent signals the archive changed (New chat, reopen).
watch(() => props.refreshKey, () => { load() })

function onDocMouseDown(e) {
  if (!open.value) return
  const el = wrapRef.value
  if (el && !el.contains(e.target)) close()
}

onMounted(() => {
  load()  // seed the count badge
  document.addEventListener('mousedown', onDocMouseDown)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
})

function formatTs(ts) {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ''
  }
}
</script>

<style scoped>
.history-wrap {
  position: relative;
  display: inline-flex;
}
/* Mirrors ChatWorkflow's .header-action so this button sits flush with the
   other header controls (scoped styles don't cross components). */
.header-action {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background-color: #222222;
  color: #dddddd;
  /* Caldera-brand hairline (mirrors ChatWorkflow's .header-action); neutral
     #222 surface stays. */
  border: 1px solid rgba(139, 0, 255, 0.3);
  border-radius: 6px;
  padding: 0.4rem 0.75rem;
  font-size: 0.82rem;
  cursor: pointer;
}
.header-action:hover:not(:disabled) {
  background-color: #2e2e2e;
  border-color: #8b00ff;
  color: #ffffff;
}
.header-action.is-open {
  background-color: #2e2e2e;
  border-color: #8b00ff;
  color: #ffffff;
}
.log-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.15rem;
  height: 1.15rem;
  padding: 0 0.32rem;
  border-radius: 999px;
  background-color: #191919;
  color: #ebebeb;
  font-size: 0.7rem;
  font-weight: 700;
  line-height: 1;
}

.history-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 60;
  width: 340px;
  max-width: calc(100vw - 2rem);
  display: flex;
  flex-direction: column;
  max-height: 60vh;
  background-color: #191919;
  border: 1px solid #333333;
  border-radius: 6px;
  box-shadow: 0 18px 55px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(139, 0, 255, 0.12);
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.55rem 0.7rem;
  background-color: #191919;
  border-bottom: 1px solid #333333;
  flex-shrink: 0;
}
.panel-title {
  font-size: 0.86rem;
  font-weight: 650;
  color: #ffffff;
}
.panel-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.panel-link {
  background: transparent;
  border: 1px solid transparent;
  color: #b5b5b5;
  font-size: 0.74rem;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  cursor: pointer;
}
.panel-link:hover {
  color: #ffffff;
  border-color: #333333;
  background-color: #222222;
}
.panel-link.is-confirming {
  color: #ffd7d7;
  border-color: rgba(220, 80, 80, 0.5);
  background-color: rgba(220, 80, 80, 0.14);
}
.panel-close {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: #222222;
  border: 1px solid #333333;
  border-radius: 4px;
  color: #dddddd;
  cursor: pointer;
}
.panel-close:hover {
  background-color: #2e2e2e;
  border-color: #8b00ff;
  color: #ffffff;
}

.panel-body {
  overflow-y: auto;
  min-height: 0;
  padding: 0.4rem;
}
.panel-empty {
  color: #888888;
  font-size: 0.82rem;
  line-height: 1.45;
  padding: 0.6rem 0.5rem;
  margin: 0;
}

.conv-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.conv-row {
  display: flex;
  align-items: stretch;
  gap: 0.35rem;
  border: 1px solid #333333;
  border-radius: 4px;
  background-color: #1b1b1b;
  overflow: hidden;
}
.conv-row:hover {
  border-color: #8b00ff;
}
.conv-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  align-items: flex-start;
  text-align: left;
  background: transparent;
  border: none;
  color: #f5f5f5;
  padding: 0.45rem 0.55rem;
  cursor: pointer;
}
.conv-main:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.conv-title {
  font-size: 0.84rem;
  font-weight: 550;
  color: #ededed;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.conv-meta {
  font-size: 0.72rem;
  color: #8f8f8f;
}
.conv-del {
  flex-shrink: 0;
  width: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: #222222;
  border: none;
  border-left: 1px solid #333333;
  color: #b5b5b5;
  cursor: pointer;
}
.conv-del:hover {
  background-color: rgba(220, 80, 80, 0.16);
  color: #ffd7d7;
}
</style>
