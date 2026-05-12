<!--
  Chat input. Fills the remaining vertical space in the chat panel (flex: 1)
  so the textarea is large by default and the surrounding layout stays stable
  whether the prompt is one line or many — no auto-grow, no jumpy reflow.
  Submits on Cmd/Ctrl+Enter; plain Enter inserts a newline.
-->
<template>
  <div class="chat-composer">
    <div v-if="examplePrompts.length && !modelValue && !disabled" class="example-row">
      <span class="example-label">Try:</span>
      <button
        v-for="(ex, i) in examplePrompts"
        :key="i"
        class="example-chip"
        type="button"
        @click="$emit('update:modelValue', ex)"
      >
        {{ truncate(ex, 80) }}
      </button>
    </div>

    <div class="composer-row">
      <textarea
        ref="textarea"
        :value="modelValue"
        @input="onInput"
        @keydown="onKeydown"
        :placeholder="placeholder"
        :disabled="disabled"
        class="composer-textarea"
      ></textarea>
      <button
        class="send-button"
        :disabled="!canSend"
        @click="submit"
        type="button"
        :title="disabled ? 'Run in progress' : 'Send (Ctrl+Enter)'"
      >
        <font-awesome-icon :icon="sendIcon" />
      </button>
    </div>
    <div class="composer-hint">
      <span>Ctrl+Enter to send · Enter for newline</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { faPaperPlane } from '@fortawesome/free-solid-svg-icons'

const props = defineProps({
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  placeholder: { type: String, default: 'Describe what you want this workflow to do…' },
  examplePrompts: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'submit'])

const textarea = ref(null)
const sendIcon = faPaperPlane

function onInput(e) {
  emit('update:modelValue', e.target.value)
}

function onKeydown(e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    submit()
  }
}

const canSend = computed(() =>
  !props.disabled && !!(props.modelValue && props.modelValue.trim())
)

function submit() {
  if (!canSend.value) return
  emit('submit')
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}
</script>

<style scoped>
.chat-composer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.9rem 1.1rem 1rem 1.1rem;
  background-color: #1c1a22;
  border-top: 1px solid rgba(158, 98, 255, 0.24);
}
.example-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  padding-bottom: 0.2rem;
}
.example-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #a99dbe;
  margin-right: 0.2rem;
}
.example-chip {
  background-color: rgba(139, 92, 246, 0.08);
  color: #cfc3ff;
  border: 1px solid rgba(169, 112, 255, 0.22);
  border-radius: 999px;
  padding: 0.3rem 0.75rem;
  font-size: 0.78rem;
  cursor: pointer;
  font-style: italic;
}
.example-chip:hover {
  background-color: rgba(139, 92, 246, 0.15);
  border-color: rgba(169, 112, 255, 0.5);
  color: #f3efff;
}
.composer-row {
  display: flex;
  align-items: stretch;
  gap: 0.6rem;
}
.composer-textarea {
  flex: 1;
  height: 140px;
  resize: none;
  background-color: #24202e;
  color: #f5f5f5;
  border: 1px solid rgba(169, 112, 255, 0.22);
  border-radius: 8px;
  padding: 0.85rem 1rem;
  font-size: 0.97rem;
  line-height: 1.5;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s ease;
}
.composer-textarea:focus {
  border-color: #a970ff;
  box-shadow: 0 0 0 2px rgba(169, 112, 255, 0.16);
}
.composer-textarea:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.send-button {
  align-self: flex-end;
  width: 44px;
  height: 44px;
  border-radius: 8px;
  border: 1px solid rgba(169, 112, 255, 0.46);
  background-color: rgba(139, 92, 246, 0.16);
  color: #f5f1ff;
  font-size: 1.05rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background-color 0.15s ease, transform 0.05s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.send-button:hover:not(:disabled) {
  background-color: rgba(169, 112, 255, 0.28);
  border-color: #b98cff;
  box-shadow: 0 0 0 2px rgba(169, 112, 255, 0.12);
  color: #ffffff;
}
.send-button:active:not(:disabled) { transform: scale(0.96); }
.send-button:not(:disabled) {
  background: linear-gradient(135deg, #7c3aed, #a855f7);
  border-color: #c084fc;
}
.send-button:disabled {
  background-color: #25212d;
  border-color: rgba(169, 112, 255, 0.2);
  color: #7d718f;
  cursor: not-allowed;
}
.composer-hint {
  font-size: 0.72rem;
  color: #857894;
  text-align: right;
  padding-right: 0.2rem;
}
</style>
