<template>
  <div class="is-flex is-justify-content-center" style="width: 100%;">
    <div style="width: 75%;">

      <!-- =========================================================
           MAIN TWO-COLUMN LAYOUT
           ========================================================= -->
      <div class="columns is-variable is-4">

        <!-- ================= LEFT: PROMPT ================= -->
        <div class="column is-two-thirds">
          <div class="box">

            <!-- Header -->
            <div class="is-flex is-align-items-center is-justify-content-space-between mb-3">
              <h2 class="title is-4 has-text-primary mb-0">
                LLM Operation Planner
              </h2>

              <span
                class="icon is-clickable"
                @click="collapsibleBoxOpen = !collapsibleBoxOpen"
              >
                <font-awesome-icon
                  :icon="['fas', collapsibleBoxOpen ? 'minus' : 'plus']"
                />
              </span>
            </div>

            <!-- Prompt Content -->
            <div v-show="collapsibleBoxOpen">
              <div v-if="uiPhase === 'idle' || uiPhase === 'finished'">

                <strong>Example Starting Prompt:</strong>
                <blockquote class="example-prompt">
                  Find some abilities that constitute a stealer adversary for
                  Linux which includes credential-access and exfiltration, then
                  create an adversary with those abilities, then create an
                  operation with the adversary.
                </blockquote>

                <div class="field">
                  <div class="control">
                    <textarea
                      v-model="inputText"
                      class="textarea"
                      rows="4"
                      placeholder="Describe the complete adversary operation you'd like to plan and execute..."
                    />
                  </div>
                </div>

                <div class="is-flex is-justify-content-space-between is-align-items-center mt-4">
                  <button
                    class="button is-light is-small"
                    @click="$emit('back')"
                  >
                    ← Back
                  </button>

                  <button
                    class="button is-primary"
                    :disabled="!inputText || isLoading || !isModelConfigValid"
                    @click="handleSubmit"
                  >
                    <span v-if="isLoading">Processing...</span>
                    <span v-else>Submit</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ================= RIGHT: MODEL CONFIG ================= -->
        <div class="column is-one-third">
          <McpModelConfigPanel
            :backend-config="globalConfig"
            config-key="llm"
            @validity="isModelConfigValid = $event"
          />
        </div>
      </div>

      <!-- =========================================================
           RAG CONTEXT
           ========================================================= -->
      <div class="box mt-5">
        <div class="is-flex is-align-items-center is-justify-content-space-between mb-3">
          <h3 class="title is-5 has-text-primary mb-0">RAG Context</h3>

          <span
            class="icon is-clickable"
            @click="ragBoxOpen = !ragBoxOpen"
          >
            <font-awesome-icon
              :icon="['fas', ragBoxOpen ? 'minus' : 'plus']"
            />
          </span>
        </div>

        <div v-show="ragBoxOpen">
          <h4 class="title is-6">CTI Context (STIX Bundles)</h4>

          <table class="table is-fullwidth is-striped is-hoverable">
            <thead>
              <tr>
                <th></th>
                <th>File</th>
                <th>Model</th>
                <th class="has-text-right">Size</th>
                <th class="has-text-centered">View</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="f in ragFiles" :key="f.filename">
                <td>
                  <input
                    type="checkbox"
                    :value="f.filename"
                    v-model="selectedRag"
                    :disabled="isLoading"
                  />
                </td>

                <td>📦 {{ f.filename }}</td>

                <td class="has-text-grey">
                  <span v-if="f.model">
                    {{ f.provider ? `${f.provider} / ${f.model}` : f.model }}
                  </span>
                  <span v-else>—</span>
                </td>

                <td class="has-text-right">
                  {{ (f.size / 1024).toFixed(1) }} KB
                </td>

                <td class="has-text-centered">
                  <button
                    class="button is-primary is-small is-light"
                    @click.stop="viewStix(f.filename)"
                  >
                    View
                  </button>
                </td>
              </tr>

              <tr v-if="!ragFiles.length">
                <td
                  colspan="5"
                  class="has-text-grey has-text-centered"
                >
                  No STIX bundles available
                </td>
              </tr>
            </tbody>
          </table>

          <p
            v-if="selectedRag.length"
            class="mt-2 is-size-7 has-text-grey"
          >
            Selected: {{ selectedRag.length }} bundle(s)
          </p>
        </div>
      </div>
    </div>

    <!-- ================= STIX MODAL ================= -->
    <StixViewerModal
      v-if="showStixModal"
      :filename="stixFilename"
      :stix="stixData"
      @close="showStixModal = false"
    />
  </div>
</template>

<script setup>
/* ============================================================
 * Imports
 * ============================================================ */
import { computed, inject, onMounted, ref } from 'vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { faMinus, faPlus } from '@fortawesome/free-solid-svg-icons'

import McpModelConfigPanel from '../components/modelSelector.vue'
import StixViewerModal from '../components/stixViewer.vue'

/* ============================================================
 * Injected Services / Global State
 * ============================================================ */
const $api = inject('$api')
const isModelConfigValid = inject('isModelConfigValid', ref(false))
const mcpGlobal = inject('mcpGlobalConfig')

const globalConfig = computed(() => mcpGlobal?.config?.value ?? {})

/* ============================================================
 * UI State
 * ============================================================ */
const collapsibleBoxOpen = ref(true)
const ragBoxOpen = ref(true)
const isLoading = ref(false)
const uiPhase = ref('idle')

/* ============================================================
 * Prompt / Execution State
 * ============================================================ */
const inputText = ref('')
const runId = ref(null)

/* ============================================================
 * RAG State
 * ============================================================ */
const ragFiles = ref([])
const selectedRag = ref([])

/* ============================================================
 * STIX Viewer State
 * ============================================================ */
const showStixModal = ref(false)
const stixData = ref(null)
const stixFilename = ref('')

/* ============================================================
 * Actions
 * ============================================================ */
async function handleSubmit() {
  isLoading.value = true

  try {
    const cfg = globalConfig.value
    const useRag = selectedRag.value.length > 0

    const payload = {
      text: inputText.value,
      type: useRag ? 'rag_planner' : 'planner',
      config: {
        provider: cfg.provider,
        model: cfg.model,
        api_base: cfg.api_base,
        api_key: cfg.api_key,
        temperature: cfg.temperature,
        max_tool_calls: cfg.max_tool_calls,
        max_tokens: cfg.max_tokens,
        rag_files: selectedRag.value,
        rag_embed_model: cfg.rag_embed_model,
        rag_top_k: cfg.rag_top_k
      }
    }

    const response = await $api.post('/plugin/mcp/execute', payload)
    runId.value = response.data.run_id
    inputText.value = ''
    uiPhase.value = 'running'
  } finally {
    isLoading.value = false
  }
}

async function fetchRagFiles() {
  const res = await fetch('/plugin/mcp/stix/list')
  const data = await res.json()
  ragFiles.value = data.files || []
}

async function viewStix(filename) {
  const res = await fetch('/plugin/mcp/stix/get_stix', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename })
  })

  const out = await res.json()
  stixData.value = out.data
  stixFilename.value = out.filename
  showStixModal.value = true
}

/* ============================================================
 * Lifecycle
 * ============================================================ */
onMounted(fetchRagFiles)
</script>

<style scoped>
.example-prompt {
  border-left: 4px solid #7a00cc;
  padding: 1rem;
  background-color: #f4f4f4;
  color: #222;
  font-style: italic;
}
</style>
