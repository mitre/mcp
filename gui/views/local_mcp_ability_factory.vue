<template>
  <div class="is-flex is-justify-content-center" style="width: 100%;">
    <div style="width: 75%;">
      <div class="columns is-variable is-4">
        <div class="column is-two-thirds">
          <div class="box">
            <div class="is-flex is-align-items-center is-justify-content-space-between mb-3">
              <h2 class="title is-4 has-text-primary mb-0">{{ props.workflow?.display_name || 'MCP Workflow' }}</h2>
              <span class="icon is-clickable" @click="collapsibleBoxOpen = !collapsibleBoxOpen">
                <font-awesome-icon :icon="['fas', collapsibleBoxOpen ? 'minus' : 'plus']" />
              </span>
            </div>

            <div v-show="collapsibleBoxOpen">
              <div v-if="uiPhase === 'idle' || uiPhase === 'finished'">
                <p v-if="props.workflow?.description" class="mb-3">{{ props.workflow.description }}</p>

                <div v-if="examplePrompts.length">
                  <strong>Example Starting Prompts:</strong>
                  <blockquote
                    v-for="(ex, i) in examplePrompts"
                    :key="i"
                    class="example-prompt"
                    @click="inputText = ex"
                    style="cursor: pointer;"
                    title="Click to use this prompt"
                  >
                    {{ ex }}
                  </blockquote>
                </div>

                <!-- Per-workflow scoped server checklist. Required servers are
                     pinned on (rendered disabled). -->
                <div v-if="serverChoices.length" class="field mt-3">
                  <label class="label">Enabled MCP Servers for this workflow</label>
                  <div class="control">
                    <label
                      v-for="srv in serverChoices"
                      :key="srv.name"
                      class="checkbox is-block mb-1"
                      :title="srv.description"
                    >
                      <input
                        type="checkbox"
                        :value="srv.name"
                        :checked="enabledServers.includes(srv.name)"
                        :disabled="srv.required"
                        @change="toggleServer(srv.name, $event.target.checked)"
                      />
                      {{ srv.display_name }}
                      <span class="has-text-grey-light is-size-7">
                        ({{ srv.name }}<span v-if="srv.required"> &middot; required</span>)
                      </span>
                    </label>
                  </div>
                </div>

                <!-- Per-workflow capability panel. Toggling a capability adds
                     it to enabled_capabilities; the capability's own settings
                     (e.g. RAG file picker) live in the right column. -->
                <div v-if="capabilityChoices.length" class="field mt-3">
                  <label class="label">Capabilities</label>
                  <div class="control">
                    <label
                      v-for="cap in capabilityChoices"
                      :key="cap.id"
                      class="checkbox is-block mb-1"
                      :title="cap.description"
                    >
                      <input
                        type="checkbox"
                        :value="cap.id"
                        :checked="enabledCapabilities.includes(cap.id)"
                        @change="toggleCapability(cap.id, $event.target.checked)"
                      />
                      {{ cap.display_name }}
                      <span class="has-text-grey-light is-size-7">({{ cap.id }})</span>
                    </label>
                  </div>
                </div>

                <div class="field mt-3">
                  <div class="control">
                    <textarea
                      v-model="inputText"
                      class="textarea"
                      rows="4"
                      placeholder="Describe what you want this workflow to do..."
                    ></textarea>
                  </div>
                </div>

                <div class="is-flex is-justify-content-space-between is-align-items-center mt-4">
                  <button class="button is-light is-small" @click="$emit('back')">
                    ← Back
                  </button>

                  <button class="button is-primary" @click="handleSubmit" :disabled="!inputText || isLoading">
                    <span v-if="isLoading">Processing...</span>
                    <span v-else>Submit</span>
                  </button>
                </div>
              </div>
            </div>

            <div class="mt-3" v-if="responseMessage || errorMessage || submittedPrompt || pollReasoning">
              <div v-if="responseMessage" class="notification is-success">
                {{ responseMessage }}
              </div>
              <div v-if="errorMessage" class="notification is-danger">
                {{ errorMessage }}
              </div>

              <div v-if="uiPhase !== 'idle' && (submittedPrompt || pollPrompt)" class="notification is-info is-light">
                <strong>Prompt:</strong>
                <p class="mt-1">{{ submittedPrompt || pollPrompt }}</p>
              </div>

              <div v-if="uiPhase !== 'idle' && pollReasoning" class="reasoning-panel mt-2">
                <strong class="reasoning-title">Reasoning</strong>
                <pre class="reasoning-pre">{{ pollReasoning }}</pre>
              </div>
            </div>

            <div v-if="!collapsibleBoxOpen" class="mt-3">
              <button class="button is-light is-small" @click="$emit('back')">
                ← Back
              </button>
            </div>
          </div>
        </div>

        <div class="column is-one-third" v-if="workflowAcceptsRag">
          <div class="box">
            <div class="is-flex is-align-items-center is-justify-content-space-between mb-3">
              <h3 class="title is-5 has-text-primary mb-0">RAG Data</h3>
              <span class="icon is-clickable" @click="ragBoxOpen = !ragBoxOpen">
                <font-awesome-icon :icon="['fas', ragBoxOpen ? 'minus' : 'plus']" />
              </span>
            </div>

            <!-- RAG-specific settings live with the RAG capability, not in
                 Global Model Config, since they only make sense when RAG is
                 in play. Bound to globalConfig.capabilitySettings.rag so
                 they persist via the same localStorage path. -->
            <div v-show="ragBoxOpen" class="field">
              <label class="label">RAG TopK</label>
              <div class="control">
                <input
                  class="input is-small"
                  type="number"
                  min="1"
                  max="30"
                  step="1"
                  v-model.number="ragSettings.topk"
                />
              </div>
            </div>
            <div v-show="ragBoxOpen" class="field">
              <label class="label">RAG Embed Model</label>
              <div class="control">
                <input
                  class="input is-small"
                  type="text"
                  v-model="ragSettings.embed_model"
                  placeholder="openai/text-embedding-3-small"
                />
              </div>
            </div>

            <div v-show="ragBoxOpen" class="field">
              <div class="file has-name is-fullwidth">
                <label class="file-label">
                  <input
                    class="file-input"
                    type="file"
                    accept=".json,application/json"
                    @change="onFileSelected"
                    :disabled="isUploading || isLoading"
                  />
                  <span class="file-cta">
                    <span class="file-icon">
                      <font-awesome-icon :icon="['fas', 'plus']" />
                    </span>
                    <span class="file-label">
                      Choose a JSON file…
                    </span>
                  </span>
                  <span class="file-name">
                    {{ selectedFile ? selectedFile.name : 'No file chosen' }}
                  </span>
                </label>
              </div>
            </div>

            <div v-show="ragBoxOpen" class="buttons">
              <button class="button is-primary"
                      @click="uploadRag"
                      :disabled="!selectedFile || isUploading">
                <span v-if="isUploading">Uploading...</span>
                <span v-else>Upload</span>
              </button>
              <button class="button"
                      @click="fetchRagFiles"
                      :disabled="isUploading || isLoading">
                Refresh
              </button>
            </div>

            <div v-show="ragBoxOpen" v-if="uploadMessage" class="notification is-success">
              {{ uploadMessage }}
            </div>
            <div v-show="ragBoxOpen" v-if="uploadError" class="notification is-danger">
              {{ uploadError }}
            </div>

            <div v-show="ragBoxOpen" class="mt-3">
              <strong>Uploaded Files</strong>
              <div class="mt-2" style="max-height: 240px; overflow: auto;">
                <label
                  v-for="f in ragFiles"
                  :key="f.filename"
                  class="checkbox mb-2 is-block"
                >
                  <input
                    type="checkbox"
                    :value="f.filename"
                    v-model="selectedRag"
                    :disabled="isUploading || isLoading"
                  />
                  <span class="ml-2">{{ f.filename }}</span>
                  <span class="is-size-7 has-text-grey"> ({{ formatBytes(f.size) }}, {{ formatDate(f.modified) }})</span>
                </label>
              </div>
              <p v-if="ragFiles.length === 0" class="has-text-grey">No files found.</p>
              <p v-else-if="selectedRag.length" class="mt-2 is-size-7">
                Selected: {{ selectedRag.length }} file(s)
              </p>
            </div>
          </div>
        </div>
      </div>

      <div v-if="uiPhase === 'running' || uiPhase === 'finished'" class="mt-4">
        <p v-if="displayedStage && displayedStage.toLowerCase() !== 'completed'" class="is-size-5 has-text-weight-medium">
          <strong>Stage: </strong> {{ displayedStage }}
        </p>

        <p><strong>Status: </strong> 
          <span v-if="pollStatus === 'RUNNING'">{{ animatedStatus }}</span>
          <span v-else>{{ pollStatus }}</span>
        </p>
      </div>

      <div v-if="uiPhase === 'running' || uiPhase === 'finished'" class="mt-5" v-show="thoughts.length">
        <div class="box">
          <h3 class="title is-5">Thoughts</h3>
          <div class="reasoning-box">
            <template v-for="(thought, idx) in thoughts" :key="idx">
              <div v-for="(sentence, sIdx) in splitSentences(thought)" :key="sIdx">
                <p v-if="!isInjectedSentence(sentence)" class="thought-line">• {{ sentence }}</p>

                <div v-if="lastAbilitySentenceKeys.has(`${idx}-${sIdx}`)">
                  <div
                    v-for="(line, aIdx) in parsedAbilityLines"
                    :key="'ability-' + sIdx + '-' + aIdx"
                    class="notification is-success mt-4 is-inline-block"
                    style="margin-left: 3rem;"
                  >
                    {{ line }}
                  </div>
                  <br>
                </div>

                <div v-if="lastAdversarySentenceKeys.has(`${idx}-${sIdx}`)">
                  <div
                    class="notification is-success mt-4 is-inline-block"
                    style="margin-left: 2rem;"
                  >
                    {{ parsedAdversaryLine.name }} - {{ parsedAdversaryLine.uuid }}
                    <div v-if="parsedAbilityLines.length" class="mt-2">
                      <div
                        v-for="(line, i) in parsedAbilityLines"
                        :key="'adv-ability-' + sIdx + '-' + i"
                        style="margin-left: 2rem;"
                      >
                        {{ line }}
                      </div>
                    </div>
                  </div>
                  <br>
                </div>

              </div>
            </template>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>


<script setup>
import { inject, ref, watch, computed, onMounted } from "vue"
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { faPlus, faMinus } from '@fortawesome/free-solid-svg-icons'

const props = defineProps({
  // Workflow registration object from /plugin/mcp/workflows. May be missing
  // when the parent shell hasn't loaded the registry yet (mounting race);
  // we guard with optional chaining throughout.
  workflow: { type: Object, default: () => ({}) },
  // Capability registration list from /plugin/mcp/capabilities. Filtered to
  // those the current workflow accepts before being shown in the UI.
  capabilities: { type: Array, default: () => [] },
})

const $api = inject("$api")
const globalConfig = inject("mcpGlobalConfig")
const availableServers = inject("mcpAvailableServers", ref([]))

// ---- Per-workflow scoped server + capability state -----------------------
// Reads/writes flow through globalConfig so localStorage persistence is
// automatic. Each map is keyed by workflow.id so a user's RANGE checkbox
// for "Plan & Execute" doesn't bleed into "Author".
const enabledServers = computed({
  get: () => globalConfig.serversByWorkflow?.[props.workflow.id] || [],
  set: (v) => {
    if (!globalConfig.serversByWorkflow) globalConfig.serversByWorkflow = {}
    globalConfig.serversByWorkflow[props.workflow.id] = v
  },
})

const enabledCapabilities = computed({
  get: () => globalConfig.capabilitiesByWorkflow?.[props.workflow.id] || [],
  set: (v) => {
    if (!globalConfig.capabilitiesByWorkflow) globalConfig.capabilitiesByWorkflow = {}
    globalConfig.capabilitiesByWorkflow[props.workflow.id] = v
  },
})

// Server choices = required (pinned-on) + optional. Required entries render
// disabled so the user can't untick them; the backend would force them on
// anyway.
const serverChoices = computed(() => {
  const wf = props.workflow || {}
  const all = availableServers.value || []
  const required = new Set(wf.required_servers || [])
  const optional = new Set(wf.optional_servers || [])
  return all
    .filter(s => required.has(s.name) || optional.has(s.name))
    .map(s => ({ ...s, required: required.has(s.name) }))
})

// Capability choices filtered to those this workflow accepts.
const capabilityChoices = computed(() => {
  const accepted = new Set(props.workflow?.accepted_capabilities || [])
  return (props.capabilities || []).filter(c => accepted.has(c.id))
})

const examplePrompts = computed(() => props.workflow?.example_prompts || [])

function toggleServer(name, checked) {
  const current = new Set(enabledServers.value)
  if (checked) current.add(name); else current.delete(name)
  enabledServers.value = [...current]
}

function toggleCapability(id, checked) {
  const current = new Set(enabledCapabilities.value)
  if (checked) current.add(id); else current.delete(id)
  enabledCapabilities.value = [...current]
}

// RAG-specific helpers used by the RAG settings panel in the right column.
const workflowAcceptsRag = computed(() =>
  (props.workflow?.accepted_capabilities || []).includes('rag')
)
const ragSettings = computed(() => {
  if (!globalConfig.capabilitySettings) globalConfig.capabilitySettings = {}
  if (!globalConfig.capabilitySettings.rag) globalConfig.capabilitySettings.rag = {}
  return globalConfig.capabilitySettings.rag
})

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
  responseMessage.value = 'Started ability creation process.'
  displayedStage.value = ''
  hasShownInitialMessage = false
  stageQueue.value = []
  stageInterval = null

  submittedPrompt.value = inputText.value?.trim() || ''

  try {
    if (pollInterval) clearInterval(pollInterval)
    if (stageInterval) clearInterval(stageInterval)

    // Build the new /execute payload. Per-workflow scoped server + capability
    // toggles come from globalConfig.serversByWorkflow and capabilitiesByWorkflow.
    // Selecting RAG files implicitly enables the rag capability for this run
    // even if the user didn't tick it explicitly, mirroring the legacy UI's
    // "attach a CTI bundle to turn RAG on" affordance.
    const filesAttached = selectedRag.value.length > 0
    const baseCaps = new Set(enabledCapabilities.value || [])
    if (filesAttached) baseCaps.add('rag')
    const finalCaps = [...baseCaps]

    const ragSettings = (globalConfig.capabilitySettings && globalConfig.capabilitySettings.rag) || {}

    const payload = {
      text: inputText.value,
      workflow_id: props.workflow.id,
      enabled_servers: enabledServers.value,
      enabled_capabilities: finalCaps,
      capability_settings: {
        rag: {
          rag_files: selectedRag.value,
          embed_model: ragSettings.embed_model || '',
          topk: ragSettings.topk,
        },
      },
      lm_config: {
        model: globalConfig.modelName,
        temperature: globalConfig.temperature,
        api_key: globalConfig.apiKey,
        max_tool_calls: globalConfig.maxToolCalls,
        max_tokens: globalConfig.maxTokens,
      },
    }

    console.log("[MCP] Submitting payload:", {
      ...payload,
      lm_config: {
        ...payload.lm_config,
        api_key: payload.lm_config.api_key
          ? `***PRESENT (${payload.lm_config.api_key.length} chars)***`
          : '***MISSING***',
      },
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

  return injects;
}

const resolvedInjects = computed(assignInjectLocations);

const lastAbilitySentenceKeys = computed(() => (resolvedInjects.value?.ability ?? new Set()));
const lastAdversarySentenceKeys = computed(() => (resolvedInjects.value?.adversary ?? new Set()));

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

function onFileSelected(e) {
  uploadMessage.value = ''
  uploadError.value = ''
  const file = e.target.files?.[0]
  if (!file) {
    selectedFile.value = null
    return
  }
  const isJson = file.type === 'application/json' || file.name.toLowerCase().endsWith('.json')
  if (!isJson) {
    selectedFile.value = null
    uploadError.value = 'Please select a .json file.'
    return
  }
  selectedFile.value = file
}

async function uploadRag() {
  if (!selectedFile.value) return
  isUploading.value = true
  uploadMessage.value = ''
  uploadError.value = ''
  try {
    const fd = new FormData()
    fd.append('file', selectedFile.value)
    const res = await $api.post('/plugin/mcp/rag/upload', fd)
    uploadMessage.value = `Uploaded ${res.data.filename} (${formatBytes(res.data.size)})`
    selectedFile.value = null
    await fetchRagFiles()
  } catch (err) {
    uploadError.value = err?.response?.data?.error || 'Upload failed.'
  } finally {
    isUploading.value = false
  }
}

async function fetchRagFiles() {
  try {
    const res = await $api.get('/plugin/mcp/rag/list')
    ragFiles.value = res.data.files || []
    const available = new Set(ragFiles.value.map(f => f.filename))
    selectedRag.value = selectedRag.value.filter(name => available.has(name))
  } catch (err) {
    uploadError.value = err?.response?.data?.error || 'Failed to fetch RAG files.'
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

onMounted(() => {
  fetchRagFiles()
})
</script>
<style scoped>
.example-prompt {
  border-left: 4px solid #7a00cc;
  padding: 1rem;
  background-color: #f4f4f4;
  color: #222;
  font-style: italic;
}

.title.is-5 + .title.is-5 {
  margin-top: 2rem;
}
.reasoning-box p {
  margin-left: 1rem;
}
.reasoning-box .notification {
  margin-bottom: .5rem;
}
.icon.is-clickable i {
  color: white !important;
  font-size: 1.25rem;
}
.thought-line {
  margin-left: 1.5rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}

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
