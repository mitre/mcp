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
         HEADER
         ====================================================== -->
    <div class="model-config__header mb-3">
      <h3 class="title is-6 has-text-primary mb-0">{{ title }}</h3>
    </div>

    <!-- ======================================================
         CONFIG FORM
         ====================================================== -->
    <div class="model-config__body">

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
        <label class="label">Temperature</label>
        <input class="input" type="number" step="0.1" min="0" max="1"
               v-model.number="local.temperature" />
        <p class="help">0 keeps extraction repeatable across runs.</p>
      </div>

      <div class="field">
        <label class="label">Max Tokens</label>
        <input class="input" type="number" v-model.number="local.max_tokens" />
      </div>

      <div class="field">
        <label class="checkbox">
          <input type="checkbox" v-model="local.offline" /> Offline mode
        </label>
        <p class="help">
          Skips the LLM entirely and extracts with spaCy and the MITRE
          taxonomy. No network calls and no API key, at lower recall. This is
          also the automatic fallback when the endpoint cannot be reached.
        </p>
      </div>

      <p class="help">
        Embeddings reuse the global model unless one is named explicitly.
      </p>
    </div>

    <!-- ======================================================
         SAVE
         ====================================================== -->
    <div class="model-config__footer is-flex is-align-items-center is-justify-content-flex-end mt-3">
      <span v-if="saveState" class="help mt-0 mr-2" :class="saveState.tone">
        {{ saveState.message }}
      </span>
      <button
        class="button is-success"
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
          offline: local.offline
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
/* The panel fills its column so it shares a baseline with the box beside
   it. The form is short enough now that it needs no scroll of its own. */
.model-config {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  width: 100%;
}

/* Pushes Save to the bottom edge, level with the box alongside. */
.model-config__body {
  flex-grow: 1;
}

/* Bulma's .help is 0.75rem, which is too tight for prose that explains what
   a setting does rather than just labelling it. */
.model-config__body :deep(.help) {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: #b5b5b5;
}
</style>
