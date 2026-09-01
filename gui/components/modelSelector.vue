<!-- ============================================================
     MODEL CONFIG PANEL (per-profile LLM settings)

     Edits one workload profile in conf/local.yml via
     /plugin/mcp/set_config. The connection belongs to the global llm
     profile, which mcp.vue's Global Model Config writes; a workload
     profile may only adjust generation settings.
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

      <!-- Read-only. The connection belongs to the global profile and a
           workload profile cannot override it, so this is always what will
           run. It is shown because extraction silently using a different
           endpoint is the failure this design removed. -->
      <div class="resolved mb-3">
        <p class="resolved__title">Extraction will use</p>
        <p class="resolved__row">
          <span class="resolved__label">Model</span>
          <span class="resolved__value">{{ resolvedModel }}</span>
        </p>
        <p class="resolved__row">
          <span class="resolved__label">Endpoint</span>
          <span class="resolved__value">{{ resolvedApiBase }}</span>
        </p>
        <p class="help mt-2">
          Set in <strong>Global Model Config</strong>. Extraction shares one
          endpoint with chat and planning; only the settings below differ.
        </p>
      </div>

      <div class="field">
        <label class="label">Temperature</label>
        <input class="input" type="number" step="0.1" min="0" max="1"
               v-model.number="local.temperature" />
        <p class="help">
          Shared with <strong>Global Model Config</strong>. 0 keeps extraction
          repeatable, because Stage 1 parses the model's own output as JSON.
        </p>
      </div>

      <div class="field">
        <label class="label">Max Tokens</label>
        <input class="input" type="number" min="1" v-model.number="local.max_tokens" />
        <p class="help">Shared with <strong>Global Model Config</strong>.</p>
      </div>

      <p v-if="validationError" class="help is-danger" role="alert">
        {{ validationError }}
      </p>

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
import { request } from '../composables/request.js'

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
const resolvedModel = computed(
  () => props.backendConfig?.resolved_model || 'not set'
)
const resolvedApiBase = computed(
  () => props.backendConfig?.resolved_api_base || 'not set'
)
// An emptied number input yields '', and '' >= 0 && '' <= 1 is true, so a
// cleared box passed validation and saved a blank into the shared llm
// profile, which has no empty-value guard of its own.
const blank = v => v === '' || v === null || v === undefined

const validationError = computed(() => {
  const t = local.temperature
  const m = local.max_tokens
  if (blank(t)) return 'Temperature is required.'
  if (!Number.isFinite(t) || t < 0 || t > 1) return 'Temperature must be between 0 and 1.'
  if (blank(m)) return 'Max Tokens is required.'
  if (!Number.isFinite(m) || m < 1) return 'Max Tokens must be 1 or more.'
  return ''
})

const isValid = computed(() => !validationError.value)


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

// The success message described the values as they were sent, so any edit
// after it retires it rather than letting it vouch for unsaved changes.
watch(
  () => ({ ...local }),
  () => { if (saveState.value?.tone === 'has-text-success') saveState.value = null },
  { deep: true }
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
    await request('Save failed', '/plugin/mcp/set_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        // temperature and max_tokens go to the global profile, so editing them
        // here is editing the same value Global Model Config shows. Two copies
        // drifted: this panel read 0 and 8192 while that one read 0.5 and
        // 24000, and nothing said which a run would use.
        llm: {
          temperature: local.temperature,
          max_tokens: local.max_tokens
        },
        // The connection is deliberately absent. Writing it back would pin a
        // copy of the global endpoint into local.yml, which is the duplication
        // this profile now inherits its way out of.
        [props.configKey]: {
          timeout: local.timeout,
          offline: local.offline
        }
      })
    })

    saveState.value = { message: 'Saved', tone: 'has-text-success' }
    emit('saved')
  } catch (e) {
    // request() already phrases this for the operator, including the expired
    // session that used to report a green "Saved" for a save that never ran.
    saveState.value = { message: e.message, tone: 'has-text-danger' }
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

.resolved {
  border: 1px solid rgba(158, 98, 255, 0.35);
  border-radius: 6px;
  background-color: #242424;
  padding: 0.75rem;
}
.resolved__title {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #a0a0a0;
  margin: 0 0 0.4rem;
}
.resolved__row {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin: 0 0 0.2rem;
}
.resolved__label {
  min-width: 4.5rem;
  color: #a0a0a0;
  font-size: 0.8125rem;
}
.resolved__value {
  color: #f5f5f5;
  word-break: break-all;
  flex: 1;
}

/* Bulma's .help is 0.75rem, which is too tight for prose that explains what
   a setting does rather than just labelling it. */
.model-config__body :deep(.help) {
  font-size: 0.8125rem;
  line-height: 1.5;
  color: #b5b5b5;
}
</style>
