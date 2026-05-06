<!--
  Scrollable conversation pane. Auto-scrolls to bottom when a new message
  is appended or the in-flight assistant message updates. The empty state
  guides the user toward submitting their first prompt.
-->
<template>
  <div ref="scroller" class="chat-transcript">
    <div v-if="!messages.length" class="empty-state">
      <h2 class="empty-title">{{ workflowName || 'MCP Workflow' }}</h2>
      <p class="empty-desc" v-if="workflowDescription">{{ workflowDescription }}</p>
      <p class="empty-hint">Type a prompt below to begin.</p>
    </div>

    <ChatMessage
      v-for="msg in messages"
      :key="msg.id"
      :message="msg"
      :split-sentences="splitSentences"
      :is-injected-sentence="isInjectedSentence"
    />
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import ChatMessage from './ChatMessage.vue'

const props = defineProps({
  messages: { type: Array, required: true },
  workflowName: { type: String, default: '' },
  workflowDescription: { type: String, default: '' },
  splitSentences: { type: Function, required: true },
  isInjectedSentence: { type: Function, required: true },
})

const scroller = ref(null)

function scrollToBottom(smooth = true) {
  const el = scroller.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

watch(() => props.messages.length, () => {
  nextTick(() => scrollToBottom(true))
})

watch(
  () => {
    const last = props.messages[props.messages.length - 1]
    return last ? `${last.status}|${last.stage}|${(last.finalResult || '').length}` : ''
  },
  () => {
    nextTick(() => {
      const el = scroller.value
      if (!el) return
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
      if (nearBottom) scrollToBottom(false)
    })
  }
)
</script>

<style scoped>
.chat-transcript {
  flex: 1;
  min-height: 0;
  padding: 1.4rem 1.6rem 1.6rem 1.6rem;
  display: flex;
  flex-direction: column;
  /* Functional scroll for long transcripts, but the bar is invisible so the
     panel doesn't read as a "scrollable subarea". Wheel + drag still work. */
  overflow-y: auto;
  scrollbar-width: none;
}
.chat-transcript::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.empty-state {
  margin: auto;
  text-align: center;
  max-width: 540px;
  padding: 2rem;
  color: #ddd;
}
.empty-title {
  font-size: 1.6rem;
  font-weight: 600;
  color: #d0d0d0;
  margin-bottom: 0.6rem;
}
.empty-desc {
  font-size: 0.97rem;
  color: #d0d0d0;
  line-height: 1.5;
  margin-bottom: 0.8rem;
}
.empty-hint {
  font-size: 0.85rem;
  color: #888888;
  font-style: italic;
}
</style>
