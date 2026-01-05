<template>
  <div class="is-flex is-justify-content-center" style="width: 100%;">
    <div style="width: 75%;">

      <!-- MAIN TWO-COLUMN LAYOUT -->
      <div class="columns is-variable is-4">

        <!-- LEFT: PROMPT -->
        <div class="column is-two-thirds">

          <!-- PROMPT BOX -->
          <div class="box">
            <div class="is-flex is-align-items-center is-justify-content-space-between mb-3">
              <h2 class="title is-4 has-text-primary mb-0">LLM Operation Planner</h2>
              <span class="icon is-clickable" @click="collapsibleBoxOpen = !collapsibleBoxOpen">
                <font-awesome-icon :icon="['fas', collapsibleBoxOpen ? 'minus' : 'plus']" />
              </span>
            </div>

            <div v-show="collapsibleBoxOpen">
              <div v-if="uiPhase === 'idle' || uiPhase === 'finished'">
                <strong>Example Starting Prompt:</strong>
                <blockquote class="example-prompt">
                  Find some abilities that constitute a stealer adversary for linux which includes credential-access and exfiltration, then create an adversary with those abilities, then create an operation with the adversary.
                </blockquote>

                <div class="field">
                  <div class="control">
                    <textarea
                      v-model="inputText"
                      class="textarea"
                      rows="4"
                      placeholder="Describe the complete adversary operation you'd like to plan and execute..."
                    ></textarea>
                  </div>
                </div>

                <div class="is-flex is-justify-content-space-between is-align-items-center mt-4">
                  <button class="button is-light is-small" @click="$emit('back')">← Back</button>
                  <button class="button is-primary" @click="handleSubmit" :disabled="!inputText || isLoading">
                    <span v-if="isLoading">Processing...</span>
                    <span v-else>Submit</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- RIGHT: RAG CONFIGURATION -->
        <div class="column is-one-third">
          <div class="box" style="position: sticky; top: 1rem;">
            <h3 class="title is-5 has-text-primary">RAG Configuration</h3>

            <div class="field">
              <label class="label">Embedding Model</label>
              <input
                class="input"
                v-model="globalConfig.ragEmbedModel"
                placeholder="e.g. text-embedding-3-large"
              />
            </div>

            <div class="field">
              <label class="label">Top-K Chunks</label>
              <input
                class="input"
                type="number"
                min="1"
                max="50"
                v-model.number="globalConfig.ragTopK"
              />
            </div>

            <p class="is-size-7 has-text-grey mt-2">
              These settings affect retrieval only, not generation.
            </p>
          </div>
      </div>
      </div>
      <!-- RAG CONTEXT (BELOW PROMPT) -->
      <div class="box mt-4">
        <div class="is-flex is-align-items-center is-justify-content-space-between mb-3">
          <h3 class="title is-5 has-text-primary mb-0">RAG Context</h3>
          <span class="icon is-clickable" @click="ragBoxOpen = !ragBoxOpen">
            <font-awesome-icon :icon="['fas', ragBoxOpen ? 'minus' : 'plus']" />
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
                <!-- VIEW BUTTON -->
                <td>
                  <div class="buttons is-centered are-small">
                  <button
                    class="button is-primary is-small is-light"
                    @click.stop="viewStix(f.filename)"
                  >
                    View
                  </button>
                  </div>
                </td>
              </tr>

              <tr v-if="!ragFiles.length">
                <td colspan="4" class="has-text-grey has-text-centered">
                  No STIX bundles available
                </td>
              </tr>
            </tbody>
          </table>

          <p v-if="selectedRag.length" class="mt-2 is-size-7 has-text-grey">
            Selected: {{ selectedRag.length }} bundle(s)
          </p>
        </div>
      </div>
    </div>
    <StixViewerModal
      v-if="showStixModal"
      :filename="stixFilename"
      :stix="stixData"
      @close="showStixModal = false"
    />
  </div>
</template>

<script setup>
import { inject, ref, watch, computed, onMounted } from "vue"
import StixViewerModal from './stixViewer.vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { faPlus, faMinus } from '@fortawesome/free-solid-svg-icons'

const $api = inject("$api")
const globalConfig = inject("mcpGlobalConfig")

const inputText = ref('')
const submittedPrompt = ref('')
const responseMessage = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

const runId = ref(null)
const pollStatus = ref('')
const pollStage = ref('')
const pollPrompt = ref('')
const pollTrajectory = ref({})
const pollReasoning = ref('')
const pollFinalResult = ref('')
const uiPhase = ref('idle')
const animatedStatus = ref('RUNNING')
const parsedAbilityLines = ref([])
const parsedAdversaryLine = ref('')
const parsedOperationLine = ref('')
const collapsibleBoxOpen = ref(true)
const ragBoxOpen = ref(true)
const stageQueue = ref([])
let stageInterval = null
const displayedStage = ref('')
let hasShownInitialMessage = false

// RAG selection (filenames selected for this run)
const selectedRag = ref([])

let dotCount = 0
let dotInterval = null

// Break each thought into individual sentences
function splitSentences(thought) {
  return thought.split(/[.?!]\s+/).map(s => s.trim()).filter(Boolean)
}
function isInjectedSentence(sentence) {
  return sentence.includes('I have successfully created') && (
    sentence.includes('abilities') || sentence.includes('adversary')
  )
}

async function handleSubmit() {
  errorMessage.value = ''
  isLoading.value = true
  pollStatus.value = 'RUNNING'
  startStatusAnimation()
  uiPhase.value = 'running'
  parsedAbilityLines.value = []
  parsedAdversaryLine.value = ''
  pollPrompt.value = ''
  pollStage.value = ''
  pollReasoning.value = ''
  pollFinalResult.value = ''
  pollTrajectory.value = {}
  runId.value = null
  responseMessage.value = 'Started creation of the operation.'
  displayedStage.value = ''
  hasShownInitialMessage = false
  stageQueue.value = []
  stageInterval = null

  submittedPrompt.value = inputText.value?.trim() || ''

  try {
    if (pollInterval) clearInterval(pollInterval)
    if (stageInterval) clearInterval(stageInterval)

    const useRag = selectedRag.value.length > 0

    // Debug: Log global config state
    console.log("[MCP Planner] Global config state:", {
      modelName: globalConfig.modelName,
      temperature: globalConfig.temperature,
      hasApiKey: !!globalConfig.apiKey,
      apiKeyLength: globalConfig.apiKey?.length || 0,
      maxToolCalls: globalConfig.maxToolCalls,
      maxTokens: globalConfig.maxTokens,
      ragEmbedModel: globalConfig.ragEmbedModel,
      ragTopK: globalConfig.ragTopK
    })

    const payload = {
      text: inputText.value,
      type: useRag ? 'rag_planner' : 'planner',
      config: {
        model: globalConfig.modelName,
        temperature: globalConfig.temperature,
        api_key: globalConfig.apiKey,
        max_tool_calls: globalConfig.maxToolCalls,
        max_tokens: globalConfig.maxTokens,
        rag_files: selectedRag.value,
        rag_embed_model: globalConfig.ragEmbedModel,
        rag_topk: globalConfig.ragTopK
      }
    }

    // Debug: Log payload with redacted API key
    console.log("[MCP Planner] Submitting payload:", {
      ...payload,
      config: {
        ...payload.config,
        api_key: payload.config.api_key ? `***PRESENT (${payload.config.api_key.length} chars)***` : '***MISSING***'
      }
    })
    const response = await $api.post('/plugin/mcp/execute', payload)

    runId.value = response.data.run_id

    pollStatusUpdates(runId.value)
    inputText.value = ''
  } catch (err) {
    errorMessage.value = err?.response?.data?.error || 'Submission failed.'
  } finally {
    isLoading.value = false
  }
}
let pollInterval = null;
let shownStages = new Set();

function pollStatusUpdates(id) {
  if (pollInterval) clearInterval(pollInterval);
  pollStatus.value = 'RUNNING';
  startStatusAnimation();

  pollInterval = setInterval(async () => {
    try {
      const res = await $api.get('/plugin/mcp/status', { params: { run_id: id } });

      pollStatus.value = res.data.status || 'unknown';
      pollPrompt.value = res.data.prompt || '';
      pollReasoning.value = res.data.reasoning || '';
      pollFinalResult.value = res.data.process_result || '';
      pollTrajectory.value = res.data.trajectory || {};

      if (pollStatus.value === 'RUNNING') {
        startStatusAnimation();
      } else {
        stopStatusAnimation();
      }

      const stage = res.data.stage;
      const stageLower = stage?.toLowerCase();

      if (
        stage &&
        !stageLower.includes('complete') &&
        stage !== displayedStage.value &&
        !shownStages.has(stage) &&
        !stageQueue.value.includes(stage)
      ) {
        if (!displayedStage.value && stageQueue.value.length === 0 && shownStages.size === 0) {
          displayedStage.value = stage;
          shownStages.add(stage);
        } else {
          stageQueue.value.push(stage);
        }
      }

      if (!stageInterval) {
        stageInterval = setInterval(() => {
          if (stageQueue.value.length > 0) {
            const next = stageQueue.value.shift();
            displayedStage.value = next;
            shownStages.add(next);
          }
        }, 8000);
      }

      if (pollStatus.value === 'FINISHED' || pollStatus.value === 'FAILED') {
        clearInterval(pollInterval);
        clearInterval(stageInterval);
        pollInterval = null;
        stageInterval = null;
        stageQueue.value = [];
        displayedStage.value = '';
        uiPhase.value = 'finished';
        collapsibleBoxOpen.value = false;
        responseMessage.value = 'Execution complete.';
      }

      const traj = res.data.trajectory;
      if (!traj) {
        return;
      }

      const advToolEntry = Object.entries(traj).find(
        ([k, v]) => k.startsWith('tool_name_') && v === 'create_adversary'
      );
      if (!advToolEntry) {
        return;
      }

      const idx = advToolEntry[0].split('_')[2];
      let args = traj[`tool_args_${idx}`];
      let observation = traj[`observation_${idx}`];

      try {
        if (typeof args === 'string') args = JSON.parse(args);
      } catch {
        return;
      }

      if (!args || !Array.isArray(args.atomic_ordering)) {
        return;
      }

      let adversaryUUID = null;
      try {
        const parsedObs = typeof observation === 'string' ? JSON.parse(observation) : observation;
        adversaryUUID = parsedObs?.adversary_id || null;
      } catch {}

      parsedAdversaryLine.value = {
        name: args.name || 'Unnamed Adversary',
        uuid: adversaryUUID || 'unknown-uuid'
      };

      const abilityUuids = args.atomic_ordering;
      const uuidToName = {};

      Object.entries(traj)
        .filter(([k]) => k.startsWith('observation_'))
        .forEach(([k, v]) => {
          let parsed;
          try {
            parsed = typeof v === 'string' ? JSON.parse(v) : v;
          } catch {
            return;
          }

          if (parsed?.ability_id && parsed?.name) {
            uuidToName[parsed.ability_id] = parsed.name;
          }

          if (Array.isArray(parsed)) {
            parsed.forEach(item => {
              let obj;
              try {
                obj = typeof item === 'string' ? JSON.parse(item) : item;
              } catch {
                return;
              }
              if (obj?.ability_id && obj?.name) {
                uuidToName[obj.ability_id] = obj.name;
              }
            });
          }
        });

      parsedAbilityLines.value = abilityUuids
        .map(uuid => {
          const name = uuidToName[uuid];
          return name;
        })
        .filter(Boolean);

      // Find operation creation entry
      const opToolEntry = Object.entries(traj).find(
        ([k, v]) => k.startsWith('tool_name_') && v === 'create_operation'
      );

      if (opToolEntry) {
        const opIdx = opToolEntry[0].split('_')[2];
        let opArgs = traj[`tool_args_${opIdx}`];

        try {
          if (typeof opArgs === 'string') opArgs = JSON.parse(opArgs);
        } catch {
          opArgs = null;
        }

        if (opArgs?.operation_name) {
          parsedOperationLine.value = {
            name: opArgs.operation_name,
            adversaryName: opArgs.adversary_name || 'unknown'
          };
        }
      }

    } catch (e) {
      clearInterval(pollInterval);
      pollInterval = null;
      errorMessage.value = 'Polling failed.';
    }
  }, 1000);
}

function startStatusAnimation() {
  if (dotInterval) return
  dotInterval = setInterval(() => {
    dotCount = (dotCount + 1) % 4
    animatedStatus.value = 'RUNNING' + '.'.repeat(dotCount)
  }, 500)
}

function stopStatusAnimation() {
  if (dotInterval) {
    clearInterval(dotInterval)
    dotInterval = null
    animatedStatus.value = pollStatus.value
  }
}

const thoughts = computed(() => {
  const traj = pollTrajectory.value
  if (!traj) return []
  return Object.entries(traj)
    .filter(([key]) => key.startsWith("thought_"))
    .sort(([a], [b]) => {
      const getIndex = (k) => parseInt(k.match(/\d+/)?.[0] || 0)
      return getIndex(a) - getIndex(b)
    })
    .map(([_, val]) => val)
})
function getMatchingSentenceKeys(matchFn) {
  const keys = [];
  thoughts.value.forEach((thought, tIdx) => {
    const sentences = splitSentences(thought);
    sentences.forEach((s, sIdx) => {
      if (matchFn(s)) keys.push(`${tIdx}-${sIdx}`);
    });
  });
  return keys;
}

const abilitySentenceKeys = computed(() =>
  getMatchingSentenceKeys((s) =>
    (s.includes('create') || s.includes('created') || s.includes('collected')) &&
    (s.includes('ability') || s.includes('abilities')) &&
    !s.includes('adversary')
  )
);

const adversarySentenceKeys = computed(() =>
  getMatchingSentenceKeys((s) =>
    (s.toLowerCase().includes('create') || s.toLowerCase().includes('created')) &&
    s.toLowerCase().includes('adversary')
  )
);

const operationSentenceKeys = computed(() =>
  getMatchingSentenceKeys((s) =>
    (s.toLowerCase().includes('create') || s.toLowerCase().includes('created')) &&
    s.toLowerCase().includes('operation')
  )
);

function assignInjectLocations() {
  const used = new Set();
  const injects = {};

  function place(label, keys) {
    for (let i = keys.length - 1; i >= 0; i--) {
      const [t, sOrig] = keys[i].split('-').map(Number);
      let s = sOrig;
      let slot = `${t}-${s}`;
      while (used.has(slot)) {
        slot = `${t}-${++s}`;
      }

      used.add(slot);
      injects[label] = new Set([slot]);
      return;
    }
  }

  place('ability', abilitySentenceKeys.value);
  place('adversary', adversarySentenceKeys.value);
  place('operation', operationSentenceKeys.value);

  return injects;
}

const resolvedInjects = computed(assignInjectLocations);

const lastAbilitySentenceKeys = computed(() => (resolvedInjects.value?.ability ?? new Set()));
const lastAdversarySentenceKeys = computed(() => (resolvedInjects.value?.adversary ?? new Set()));
const lastOperationSentenceKeys = computed(() => (resolvedInjects.value?.operation ?? new Set()));

watch(responseMessage, (newVal, oldVal) => {
  if (newVal && newVal !== oldVal) {
     if (!hasShownInitialMessage) {
      hasShownInitialMessage = true;
      return;
    }
    setTimeout(() => {
      if (responseMessage.value === newVal) {
        responseMessage.value = ''
      }
    }, 2000)
  }
})

const selectedFile = ref(null)
const isUploading = ref(false)
const ragFiles = ref([])
const uploadMessage = ref('')
const uploadError = ref('')
// STIX viewer modal state
const showStixModal = ref(false)
const stixData = ref(null)
const stixFilename = ref('')

async function fetchRagFiles() {
  try {
    const res = await fetch('/plugin/mcp/stix/list')
    if (!res.ok) throw new Error('Failed to fetch STIX list')

    const data = await res.json()

    ragFiles.value = data.files || []

    const available = new Set(ragFiles.value.map(f => f.filename))
    selectedRag.value = selectedRag.value.filter(name => available.has(name))

  } catch (err) {
    uploadError.value = err.message || 'Failed to fetch RAG files.'
  }
}

function formatBytes(bytes) {
  if (bytes === 0 || bytes == null) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString()
  } catch {
    return iso
  }
}

// Single stix view modal
async function viewStix(filename) {
  const res = await fetch('/plugin/mcp/stix/get_stix', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename })
  })

  const out = await res.json()
  if (!res.ok) throw new Error(out?.error || 'Failed to load STIX')

  stixData.value = out.data
  stixFilename.value = out.filename
  showStixModal.value = true
}

onMounted(() => {
  fetchRagFiles()

  // Ensure RAG config fields are initialized so v-model renders
  if (globalConfig.ragEmbedModel == null) {
    globalConfig.ragEmbedModel = ''
  }

  if (globalConfig.ragTopK == null) {
    globalConfig.ragTopK = 5
  }
})
</script>
<style scoped>
.example-prompt {
  border-left: 4px solid #7a00cc;
  padding: 1rem;
  background-color: #f4f4f4;
  color: #222; /* darker text for better contrast */
  font-style: italic;
}

.title.is-5 + .title.is-5 {
  margin-top: 2rem; /* Ensure vertical spacing between Thoughts and Reasoning headings */
}
.reasoning-box p {
  margin-left: 1rem; /* indent bullet-pointed sentences */
}
.reasoning-box .notification {
  margin-bottom: .5rem; /* Adjust spacing between items */
}
.icon.is-clickable i {
  color: white !important;
  font-size: 1.25rem;
}
.thought-line {
  margin-left: 1.5rem;  /* indent */
  margin-bottom: 0.5rem;  /* vertical spacing between bullets */
  line-height: 1.4;  /* slightly more legible */
}

/* Reasoning panel to match palette */
.reasoning-panel {
  border-left: 4px solid #7a00cc;
  background-color: #f4f4f4;
  color: #222;
  padding: 1rem;
  border-radius: 6px;
}
.reasoning-title {
  color: #363636;
}
.reasoning-pre {
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  background-color: #ffffff;
  color: #222;
  padding: 0.75rem;
  border-radius: 4px;
  margin-top: 0.5rem;
  max-height: 260px;
  overflow: auto;
  border: 1px solid #e6e6e6;
}
</style>
