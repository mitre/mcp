<!-- ============================================================
     MODEL CONFIG PANEL (per-profile LLM settings)

     Edits one server-side profile in conf/local.yml via
     /plugin/mcp/set_config. Distinct from mcp.vue's Global Model
     Config, which is browser-local and only rides along on
     /execute requests.
     ============================================================ -->
<template>
  <div class="box model-config">

    <!-- ======================================================
         HEADER / DISCLOSURE
         ====================================================== -->
    <div
      class="model-config__header is-flex is-justify-content-space-between is-align-items-center"
      :class="{ 'mb-3': expanded }"
      role="button"
      tabindex="0"
      :aria-expanded="String(expanded)"
      @click="expanded = !expanded"
      @keydown.enter.prevent="expanded = !expanded"
      @keydown.space.prevent="expanded = !expanded"
    >
      <h3 class="title is-6 has-text-primary mb-0">{{ title }}</h3>

      <span class="icon">
        <svg v-if="expanded" viewBox="0 0 448 512">
          <path
            fill="currentColor"
            d="M432 256c0 17.7-14.3 32-32 32H48c-17.7 0-32-14.3-32-32s14.3-32 32-32h352c17.7 0 32 14.3 32 32z"
          />
        </svg>
        <svg v-else viewBox="0 0 448 512">
          <path
            fill="currentColor"
            d="M256 80c17.7 0 32 14.3 32 32v112h112c17.7 0 32 14.3 32 32s-14.3 32-32 32H288v112c0 17.7-14.3 32-32 32s-32-14.3-32-32V288H112c-17.7 0-32-14.3-32-32s14.3-32 32-32h112V112c0-17.7 14.3-32 32-32z"
          />
        </svg>
      </span>
    </div>

    <!-- ======================================================
         CONFIG FORM
         ====================================================== -->
    <div v-if="expanded" class="model-config__body">

      <!-- Provider, model and endpoint are not repeated here. This profile
           layers over the global one, so they are set once in Global Model
           Config and inherited. Only what extraction needs differently
           lives below. -->
      <p class="help mb-3">
        Endpoint, model and credentials come from
        <strong>Global Model Config</strong>. These override them for
        extraction only.
      </p>

      <div class="field">
        <label class="label is-small">Temperature</label>
        <input class="input is-small" type="number" step="0.1" min="0" max="1"
               v-model.number="local.temperature" />
      </div>

      <div class="field">
        <label class="label is-small">Max Tokens</label>
        <input class="input is-small" type="number" v-model.number="local.max_tokens" />
      </div>

      <div class="field">
        <label class="checkbox is-size-7">
          <input type="checkbox" v-model="local.offline" /> Offline mode
        </label>
      </div>

      <div class="field">
        <label class="checkbox is-size-7">
          <input type="checkbox" v-model="local.use_mock" /> Use mock responses
        </label>
      </div>

      <p class="help">
        Embeddings reuse the global model unless one is named explicitly.
      </p>
    </div>

    <!-- ======================================================
         SAVE
         ====================================================== -->
    <div v-if="expanded" class="model-config__footer is-flex is-align-items-center is-justify-content-flex-end mt-3">
      <span v-if="saveState" class="help mt-0 mr-2" :class="saveState.tone">
        {{ saveState.message }}
      </span>
      <button
        class="button is-success is-small"
        :disabled="!isValid || saving"
        :class="{ 'is-loading': saving }"
        @click="save"
      >
        Save
      </button>
    </div>
  </div>
</template>

<script setup>
/* ============================================================
 * Imports
 * ============================================================ */
import { computed, reactive, ref, watch } from 'vue'

/* ============================================================
 * Props / Emits
 * ============================================================ */
const props = defineProps({
  backendConfig: { type: Object, required: true },
  configKey: { type: String, default: 'llm' },
  title: { type: String, default: 'Model Config' }
})

const emit = defineEmits(['saved'])

/* ============================================================
 * State
 * ============================================================ */
const expanded = ref(false)
const local = reactive({})
const saving = ref(false)
const saveState = ref(null)

/* ============================================================
 * Validation
 *
 * Every field here is an optional override with a shipped default, and
 * provider and model now live on the global profile, so there is nothing
 * left to require. Demanding a field this panel does not edit would leave
 * Save permanently disabled.
 * ============================================================ */
const isValid = computed(
  () => local.temperature === null || local.temperature === undefined
    ? true
    : local.temperature >= 0 && local.temperature <= 1
)


/* ============================================================
 * Sync
 * ============================================================ */
// Seed once from the first non-empty payload. The parent passes {} until
// its fetch lands, and a later re-seed would discard in-progress edits.
let seeded = false

watch(
  () => props.backendConfig,
  v => {
    if (seeded || !v || !Object.keys(v).length) return
    Object.assign(local, v)
    seeded = true
  },
  { deep: true, immediate: true }
)

/* ============================================================
 * Persist
 * ============================================================ */
async function save() {
  if (!isValid.value || saving.value) return

  saving.value = true
  saveState.value = null

  try {
    // Only the fields this panel edits. conf/local.yml is deep-merged over
    // default.yml, so omitted keys keep their shipped defaults.
    const res = await fetch('/plugin/mcp/set_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        // Connection fields are deliberately absent. Writing them back would
        // pin a copy of the global endpoint into local.yml, which is the
        // duplication this profile now inherits its way out of.
        [props.configKey]: {
          temperature: local.temperature,
          max_tokens: local.max_tokens,
          timeout: local.timeout,
          offline: local.offline,
          use_mock: local.use_mock
        }
      })
    })

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    saveState.value = { message: 'Saved', tone: 'has-text-success' }
    emit('saved')
  } catch (e) {
    saveState.value = { message: `Save failed: ${e.message}`, tone: 'has-text-danger' }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
/* ============================================================
 * STICKY SIDEBAR
 * ============================================================ */
.model-config {
  position: sticky;
  top: 1rem;
  display: flex;
  flex-direction: column;
  /* Without a viewport-bound ceiling a long form scrolls its own Save
     button off-screen, since the box itself never scrolls. */
  max-height: calc(100vh - 2rem);
}

.model-config__header {
  cursor: pointer;
}

.model-config__body {
  /* Flex children default to min-height:auto and refuse to shrink,
     which would defeat the overflow. */
  min-height: 0;
  overflow-y: auto;
}
</style>
