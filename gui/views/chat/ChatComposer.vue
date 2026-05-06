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
        <font-awesome-icon :icon="['fas', 'paper-plane']" />
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

const props = defineProps({
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  placeholder: { type: String, default: 'Describe what you want this workflow to do…' },
  examplePrompts: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'submit'])

const textarea = ref(null)

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
  background-color: #1f1f1f;
  border-top: 1px solid #3a3a3a;
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
  color: #888888;
  margin-right: 0.2rem;
}
.example-chip {
  background-color: #2a2a2a;
  color: #a8a8a8;
  border: 1px solid #3a3a3a;
  border-radius: 999px;
  padding: 0.3rem 0.75rem;
  font-size: 0.78rem;
  cursor: pointer;
  font-style: italic;
}
.example-chip:hover { background-color: #2c2c2c; color: #d0d0d0; }
.composer-row {
  display: flex;
  align-items: stretch;
  gap: 0.6rem;
}
.composer-textarea {
  flex: 1;
  height: 140px;
  resize: none;
  background-color: #2a2a2a;
  color: #f5f5f5;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 0.85rem 1rem;
  font-size: 0.97rem;
  line-height: 1.5;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s ease;
}
.composer-textarea:focus {
  border-color: #555555;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.08);
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
  border: 1px solid #3a3a3a;
  background-color: #2c2c2c;
  color: #d0d0d0;
  font-size: 1.05rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background-color 0.15s ease, transform 0.05s ease, border-color 0.15s ease;
}
.send-button:hover:not(:disabled) { background-color: #3a3a3a; border-color: #555555; color: #f0f0f0; }
.send-button:active:not(:disabled) { transform: scale(0.96); }
.send-button:disabled { background-color: #2a2a2a; color: #555555; cursor: not-allowed; }
.composer-hint {
  font-size: 0.72rem;
  color: #666666;
  text-align: right;
  padding-right: 0.2rem;
}
</style>
