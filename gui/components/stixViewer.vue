<!-- ============================================================
     STIX VIEWER MODAL
     ============================================================ -->
<template>
  <div class="modal is-active">
    <div class="modal-background" @click="closeModal" />

    <div class="modal-card" style="width: 90%; max-height: 90vh;">
      <!-- Header -->
      <header class="modal-card-head">
        <p class="modal-card-title">
          STIX Object — {{ filename }}
        </p>
        <button
          class="delete"
          aria-label="close"
          @click="closeModal"
        />
      </header>

      <!-- Body -->
      <section class="modal-card-body stix-json">
        <pre>{{ prettyJson }}</pre>
      </section>

      <!-- Footer -->
      <footer class="modal-card-foot is-justify-content-flex-end">
        <button class="button" @click="closeModal">
          Close
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
/* ============================================================
 * Imports
 * ============================================================ */
import { computed } from 'vue'

/* ============================================================
 * Props
 * ============================================================ */
const props = defineProps({
  filename: {
    type: String,
    required: true
  },
  stix: {
    type: Object,
    required: true
  }
})

/* ============================================================
 * Emits
 * ============================================================ */
const emit = defineEmits(['close'])

/* ============================================================
 * Computed
 * ============================================================ */
const prettyJson = computed(() =>
  JSON.stringify(props.stix, null, 2)
)

/* ============================================================
 * Handlers
 * ============================================================ */
function closeModal() {
  emit('close')
}
</script>

<style scoped>
/* ============================================================
 * STIX JSON VIEWER
 * ============================================================ */
.stix-json {
  max-height: 70vh;
  overflow: auto;
  padding: 1rem;

  background: #0f172a;
  color: #e5e7eb;

  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco,
               Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.85rem;
  line-height: 1.5;

  border-radius: 6px;
}
</style>
