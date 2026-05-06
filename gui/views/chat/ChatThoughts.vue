<!--
  Collapsible "Thoughts & reasoning" panel attached to an assistant message.
  Defaults to collapsed; clicking the header expands the full reasoning trace
  with each thought as a bullet, plus the inline ability/adversary cards
  that the original UI surfaced.
-->
<template>
  <div class="chat-thoughts" v-if="hasContent">
    <button class="thoughts-toggle" @click="open = !open" type="button">
      <font-awesome-icon :icon="['fas', open ? 'chevron-down' : 'chevron-right']" />
      <span class="toggle-label">
        {{ open ? 'Hide' : 'Show' }} thoughts &amp; reasoning
      </span>
      <span class="toggle-count" v-if="thoughts.length">
        {{ thoughts.length }} step{{ thoughts.length === 1 ? '' : 's' }}
      </span>
    </button>

    <div v-if="open" class="thoughts-body">
      <template v-for="(thought, tIdx) in thoughts" :key="tIdx">
        <div v-for="(sentence, sIdx) in splitSentences(thought)" :key="sIdx">
          <p v-if="!isInjectedSentence(sentence)" class="thought-line">
            • {{ sentence }}
          </p>
        </div>
      </template>

      <div v-if="adversary" class="inline-card">
        <strong>Adversary:</strong> {{ adversary.name }}
        <span class="muted"> &middot; {{ adversary.uuid }}</span>
        <ul v-if="abilityNames.length" class="inline-list">
          <li v-for="(name, i) in abilityNames" :key="i">{{ name }}</li>
        </ul>
      </div>

      <div v-else-if="abilityNames.length" class="inline-card">
        <strong>Abilities created:</strong>
        <ul class="inline-list">
          <li v-for="(name, i) in abilityNames" :key="i">{{ name }}</li>
        </ul>
      </div>

      <div v-if="reasoning" class="reasoning-block">
        <div class="reasoning-label">Final reasoning</div>
        <pre>{{ reasoning }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'

const props = defineProps({
  thoughts: { type: Array, default: () => [] },
  reasoning: { type: String, default: '' },
  adversary: { type: Object, default: null },
  abilityNames: { type: Array, default: () => [] },
  splitSentences: { type: Function, required: true },
  isInjectedSentence: { type: Function, required: true },
  defaultOpen: { type: Boolean, default: false },
})

const open = ref(props.defaultOpen)

const hasContent = computed(() =>
  props.thoughts.length > 0 ||
  props.reasoning ||
  props.adversary ||
  props.abilityNames.length > 0
)
</script>

<style scoped>
.chat-thoughts {
  margin-top: 0.6rem;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  background-color: #1f1f1f;
}
.thoughts-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.85rem;
  background: transparent;
  border: none;
  color: #a8a8a8;
  cursor: pointer;
  font-size: 0.85rem;
  text-align: left;
}
.thoughts-toggle:hover { background-color: rgba(255, 255, 255, 0.04); }
.toggle-label { flex: 1; }
.toggle-count {
  font-size: 0.72rem;
  color: #888888;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.thoughts-body {
  padding: 0.4rem 1rem 0.9rem 1rem;
  border-top: 1px solid #2c2c2c;
  color: #ddd;
}
.thought-line {
  margin: 0.35rem 0 0.35rem 0.5rem;
  font-size: 0.92rem;
  line-height: 1.5;
  color: #ddd;
}
.inline-card {
  margin: 0.7rem 0;
  padding: 0.7rem 0.9rem;
  background-color: #2c2c2c;
  border-left: 3px solid #7a7a7a;
  border-radius: 4px;
  color: #f5f5f5;
}
.inline-card .muted { color: #a08cc7; font-size: 0.82rem; }
.inline-list {
  margin: 0.4rem 0 0 1.2rem;
  list-style: disc outside;
  color: #ddd;
}
.inline-list li { margin: 0.15rem 0; }
.reasoning-block {
  margin-top: 0.8rem;
  background-color: #2a2a2a;
  border-radius: 4px;
  padding: 0.6rem 0.8rem;
}
.reasoning-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #7a7a7a;
  margin-bottom: 0.4rem;
}
.reasoning-block pre {
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  background: transparent;
  color: #e8e8e8;
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.45;
}
</style>
