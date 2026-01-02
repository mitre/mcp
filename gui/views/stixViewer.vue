<template>
  <div class="modal is-active">
    <div class="modal-background" @click="close" />

    <div class="modal-card" style="width: 90%; max-height: 90vh;">
      <header class="modal-card-head">
        <p class="modal-card-title">
          STIX Object — {{ filename }}
        </p>
        <button class="delete" aria-label="close" @click="close" />
      </header>

      <section class="modal-card-body stix-json">
        <pre>{{ prettyJson }}</pre>
      </section>


      <footer class="modal-card-foot is-justify-content-flex-end">
        <button class="button" @click="close">Close</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue"
const props = defineProps({
  filename: { type: String, required: true },
  stix: { type: Object, required: true }
})


const prettyJson = computed(() =>
  JSON.stringify(props.stix, null, 2)
)

const emit = defineEmits(['close'])

function close() {
  emit('close')
}

</script>

<style scoped>
.stix-json {
  max-height: 70vh;
  overflow: auto;
  background: #0f172a;
  color: #e5e7eb;
  padding: 1rem;
  font-family: monospace;
  font-size: 0.85rem;
  border-radius: 6px;
}
</style>