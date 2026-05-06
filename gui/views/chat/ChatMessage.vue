<!--
  One message in the transcript. Two flavours:
  - role="user": right-aligned bubble showing the prompt the user submitted.
  - role="assistant": left-aligned panel showing either a loading state, the
    rendered process_result, or an error, plus a collapsible thoughts panel.
-->
<template>
  <div class="chat-message" :class="`role-${role}`">
    <div class="message-bubble">
      <div class="message-meta">
        <span class="role-tag">{{ role === 'user' ? 'You' : 'Assistant' }}</span>
        <span v-if="message.timestamp" class="timestamp">{{ formattedTime }}</span>
      </div>

      <!-- User prompt -->
      <div v-if="role === 'user'" class="message-text user-text">
        {{ message.text }}
      </div>

      <!-- Assistant: still running -->
      <ChatLoadingState
        v-else-if="message.status === 'RUNNING'"
        :stage="message.stage"
        label="Thinking"
      />

      <!-- Assistant: failed -->
      <div v-else-if="message.status === 'FAILED'" class="error-text">
        <strong>Run failed.</strong>
        <p v-if="message.errorMessage" class="mt-1">{{ message.errorMessage }}</p>
      </div>

      <!-- Assistant: finished -->
      <div v-else class="assistant-body">
        <div
          v-if="formattedResult"
          class="result-content"
          v-html="formattedResult"
        ></div>
        <p v-else class="muted">No result returned.</p>
      </div>

      <!-- Thoughts panel for assistant messages with trajectory data -->
      <ChatThoughts
        v-if="role === 'assistant' && message.status !== 'RUNNING'"
        :thoughts="message.thoughts || []"
        :reasoning="message.reasoning || ''"
        :adversary="message.adversary || null"
        :ability-names="message.abilityNames || []"
        :split-sentences="splitSentences"
        :is-injected-sentence="isInjectedSentence"
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatProcessResult } from '../format_result.js'
import ChatLoadingState from './ChatLoadingState.vue'
import ChatThoughts from './ChatThoughts.vue'

const props = defineProps({
  message: { type: Object, required: true },
  // Helpers come down from parent so the trajectory composable lives in
  // exactly one place.
  splitSentences: { type: Function, default: (t) => [String(t)] },
  isInjectedSentence: { type: Function, default: () => false },
})

const role = computed(() => props.message.role || 'assistant')
const formattedResult = computed(() => formatProcessResult(props.message.finalResult || ''))

const formattedTime = computed(() => {
  if (!props.message.timestamp) return ''
  try {
    const d = new Date(props.message.timestamp)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
})
</script>

<style scoped>
.chat-message {
  display: flex;
  width: 100%;
  margin-bottom: 1.4rem;
}
.role-user { justify-content: flex-end; }
.role-assistant { justify-content: flex-start; }

.message-bubble {
  max-width: 85%;
  padding: 0.85rem 1.1rem;
  border-radius: 10px;
  background-color: #2c2c2c;
  border: 1px solid #3a3a3a;
  color: #f5f5f5;
}
.role-user .message-bubble {
  background-color: #2c2c2c;
  border-color: #3a3a3a;
}
.role-assistant .message-bubble {
  background-color: #252525;
  border-color: #3a3a3a;
  width: 100%;
  max-width: 100%;
}

.message-meta {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  margin-bottom: 0.4rem;
  font-size: 0.72rem;
}
.role-tag {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #888888;
  font-weight: 600;
}
.timestamp { color: #888888; }

.message-text {
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.5;
  color: #f5f5f5;
}
.user-text { font-size: 0.97rem; }

.assistant-body { color: #f5f5f5; }
.error-text {
  color: #ffb3b3;
  background-color: rgba(255, 80, 80, 0.08);
  border-left: 3px solid #ff6464;
  padding: 0.7rem 0.9rem;
  border-radius: 4px;
}
.muted { color: #888888; font-style: italic; }

.result-content {
  background-color: #252525;
  color: #f5f5f5;
  padding: 0.5rem 0;
  line-height: 1.55;
}
.result-content :deep(p) { margin: 0 0 0.5rem 0; color: #f5f5f5; }
.result-content :deep(p:last-child) { margin-bottom: 0; }
.result-content :deep(ul) {
  margin: 0.35rem 0 0.6rem 1.5rem;
  padding: 0;
  list-style: disc outside;
}
.result-content :deep(ul ul) {
  margin-top: 0.15rem;
  margin-bottom: 0.15rem;
  list-style: circle outside;
}
.result-content :deep(li) { margin: 0.15rem 0; color: #f5f5f5; }
.result-content :deep(li::marker) { color: #888888; }
.result-content :deep(strong) { color: #d0d0d0 !important; font-weight: 700; }
</style>
