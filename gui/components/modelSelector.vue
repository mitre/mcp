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

      <div class="field" v-for="f in requiredFields" :key="f.key">
        <label class="label is-small">{{ f.label }}</label>
        <input
          class="input is-small"
          :class="{ 'is-danger': !local[f.key] }"
          v-model="local[f.key]"
        />
        <p v-if="!local[f.key]" class="help is-danger">Required</p>
      </div>

      <div class="field">
        <label class="label is-small">API Base URL</label>
        <input class="input is-small" v-model="local.api_base" placeholder="Optional override" />
        <p class="help">Blank falls back to <code>{{ apiBaseEnv }}</code>.</p>
      </div>

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
        The API key is never written to disk. It resolves at runtime from
        <code>{{ apiKeyEnv }}</code>.
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
 * Only the fields set_config actually persists are required.
 * api_base and api_key resolve from the environment, so demanding
 * them here left Save permanently disabled.
 * ============================================================ */
const requiredFields = [
  { key: 'provider', label: 'Provider' },
  { key: 'model', label: 'Model' }
]

const isValid = computed(() => requiredFields.every(f => !!local[f.key]))

const apiBaseEnv = computed(() => props.backendConfig?.api_base_env || 'MCP_LLM_API_BASE')
const apiKeyEnv = computed(() => props.backendConfig?.api_key_env || 'MCP_LLM_API_KEY')

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
        [props.configKey]: {
          provider: local.provider,
          model: local.model,
          api_base: local.api_base || '',
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
