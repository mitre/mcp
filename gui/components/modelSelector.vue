<!-- ============================================================
     MODEL CONFIG PANEL (LLM / CTI / RAG)
     ============================================================ -->
<template>
  <div
    class="box global-model-config"
    :class="{ collapsed: !useOverride }"
    style="position: sticky; top: 1rem;"
  >
    <!-- ======================================================
         HEADER / TOGGLE
         ====================================================== -->
    <div
      class="is-flex is-justify-content-space-between is-align-items-center mb-3"
      style="cursor: pointer;"
      @click="useOverride = !useOverride"
    >
      <h3 class="title is-5 has-text-primary mb-0">
        Global Model Config
      </h3>

      <span class="icon">
        <svg v-if="useOverride" viewBox="0 0 448 512">
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
    <div v-if="useOverride">

      <!-- Required -->
      <div class="field" v-for="f in requiredFields" :key="f.key">
        <label class="label">{{ f.label }}</label>
        <input
          class="input"
          :class="{ 'is-danger': !local[f.key] }"
          v-model="local[f.key]"
        />
        <p v-if="!local[f.key]" class="help is-danger">Required</p>
      </div>

      <!-- Numeric -->
      <div class="field">
        <label class="label">Temperature</label>
        <input class="input" type="number" step="0.1" min="0" max="1"
               v-model.number="local.temperature" />
      </div>

      <div class="field">
        <label class="label">Top-P</label>
        <input class="input" type="number" step="0.1" min="0" max="1"
               v-model.number="local.top_p" />
      </div>

      <div class="field">
        <label class="label">Max Tokens</label>
        <input class="input" type="number" v-model.number="local.max_tokens" />
      </div>

      <div class="field">
        <label class="label">Max Tool Calls</label>
        <input class="input" type="number" v-model.number="local.max_tool_calls" />
      </div>

      <!-- Flags -->
      <div class="field">
        <label class="checkbox">
          <input type="checkbox" v-model="local.stream" /> Stream responses
        </label>
      </div>

      <div class="field">
        <label class="checkbox">
          <input type="checkbox" v-model="local.offline" /> Offline mode
        </label>
      </div>

      <div class="field">
        <label class="checkbox">
          <input type="checkbox" v-model="local.use_mock" /> Use mock responses
        </label>
      </div>

      <!-- RAG -->
      <hr>

      <div class="field">
        <label class="label">RAG Embed Model</label>
        <input class="input" v-model="local.rag_embed_model" />
      </div>

      <div class="field">
        <label class="label">RAG Top-K</label>
        <input class="input" type="number" v-model.number="local.rag_top_k" />
      </div>

    </div>

    <!-- ======================================================
         SAVE
         ====================================================== -->
    <div class="is-flex is-justify-content-flex-end mt-3">
      <button
        class="button is-success is-small"
        :disabled="!useOverride || !isValid"
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
  configKey: { type: String, default: 'llm' }
})

const emit = defineEmits(['saved', 'update', 'validity'])

/* ============================================================
 * State
 * ============================================================ */
const useOverride = ref(false)
const local = reactive({})

/* ============================================================
 * Validation
 * ============================================================ */
const requiredFields = [
  { key: 'provider', label: 'Provider' },
  { key: 'model', label: 'Model' },
  { key: 'api_base', label: 'API Base URL' },
  { key: 'api_key', label: 'API Key' }
]

const isValid = computed(() =>
  requiredFields.every(f => !!local[f.key])
)

/* ============================================================
 * Sync / Emit
 * ============================================================ */
watch(local, () => {
  emit('update', useOverride.value ? local : props.backendConfig)
}, { deep: true })

watch(isValid, v => emit('validity', v), { immediate: true })

watch(
  () => props.backendConfig,
  v => {
    if (!useOverride.value && v) {
      Object.assign(local, v)
    }
  },
  { deep: true, immediate: true }
)
/* ============================================================
 * Persist
 * ============================================================ */
async function save() {
  if (!isValid.value) return
  if (local.rag_embed_model == null) local.rag_embed_model = ''
  if (local.rag_top_k == null) local.rag_top_k = 5
  await fetch('/plugin/mcp/set_config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      [props.configKey]: {
        provider: local.provider,
        model: local.model,
        api_base: local.api_base,
        api_key: local.api_key,
        temperature: local.temperature,
        top_p: local.top_p,
        max_tokens: local.max_tokens,
        timeout: local.timeout,
        offline: local.offline,
        use_mock: local.use_mock,
        max_tool_calls: local.max_tool_calls,
        rag_embed_model: local.rag_embed_model,
        rag_top_k: local.rag_top_k
      }
    })
  })

  emit('saved')
}
</script>

<style scoped>
/* ============================================================
 * COLLAPSE BEHAVIOR
 * ============================================================ */
.global-model-config.collapsed {
  background: transparent;
  box-shadow: none;
  padding-bottom: 0;
}

.global-model-config.collapsed > *:not(:first-child) {
  display: none;
}
</style>
