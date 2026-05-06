<!--
  Visible while a run is in flight. Shows a pulsing dot, the current stage
  name from the backend, and an animated "RUNNING..." indicator. This is
  the user's main signal that the model is still working.
-->
<template>
  <div class="chat-loading">
    <div class="loading-row">
      <span class="dot dot-a"></span>
      <span class="dot dot-b"></span>
      <span class="dot dot-c"></span>
      <span class="loading-text">{{ animatedLabel }}</span>
    </div>
    <p v-if="displayedStage" class="stage-text">
      <span class="stage-label">Stage</span>
      <span class="stage-name">{{ displayedStage }}</span>
    </p>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps({
  stage: { type: String, default: '' },
  label: { type: String, default: 'Thinking' },
})

// Throttle stage updates: backend may emit multiple stage transitions in
// quick succession; we want each one visible long enough to read.
const STAGE_DWELL_MS = 6000
const displayedStage = ref('')
const queue = []
let dwellTimer = null
const shown = new Set()

watch(() => props.stage, (next) => {
  if (!next) return
  const lower = next.toLowerCase()
  if (lower.includes('complete')) return
  if (next === displayedStage.value || shown.has(next) || queue.includes(next)) return

  if (!displayedStage.value && queue.length === 0) {
    displayedStage.value = next
    shown.add(next)
    _scheduleAdvance()
  } else {
    queue.push(next)
  }
}, { immediate: true })

function _scheduleAdvance() {
  if (dwellTimer) return
  dwellTimer = setInterval(() => {
    if (queue.length === 0) return
    const next = queue.shift()
    displayedStage.value = next
    shown.add(next)
  }, STAGE_DWELL_MS)
}

// Animated dot label. Three dots cycle 0 → 3 every 500ms.
const animatedLabel = ref(props.label)
let dotTimer = null
let dotCount = 0
function _startDots() {
  if (dotTimer) return
  dotTimer = setInterval(() => {
    dotCount = (dotCount + 1) % 4
    animatedLabel.value = props.label + '.'.repeat(dotCount)
  }, 500)
}
_startDots()

onUnmounted(() => {
  if (dwellTimer) clearInterval(dwellTimer)
  if (dotTimer) clearInterval(dotTimer)
})
</script>

<style scoped>
.chat-loading {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 0.9rem 1.1rem;
  background-color: rgba(255, 255, 255, 0.04);
  border-left: 3px solid #7a7a7a;
  border-radius: 6px;
  color: #ddd;
}
.loading-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.loading-text {
  font-size: 0.95rem;
  color: #f5f5f5;
  letter-spacing: 0.02em;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: #7a7a7a;
  display: inline-block;
  animation: pulse 1.2s infinite ease-in-out;
}
.dot-a { animation-delay: 0s; }
.dot-b { animation-delay: 0.2s; }
.dot-c { animation-delay: 0.4s; }
@keyframes pulse {
  0%, 80%, 100% { opacity: 0.25; transform: scale(0.85); }
  40%           { opacity: 1;    transform: scale(1.05); }
}
.stage-text {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.85rem;
  margin: 0;
}
.stage-label {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #7a7a7a;
  font-weight: 600;
  font-size: 0.72rem;
}
.stage-name {
  color: #f5f5f5;
}
</style>
