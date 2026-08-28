<template>
  <div class="content">
    <div v-if="!selectedPath">
      <h2 class="title is-3">Caldera MCP: AI-Powered Operations</h2>
      <hr />
    </div>

    <!-- Main Layout: Cards on Left, Config on Right -->
    <div v-if="!selectedPath" class="columns" style="margin: 0 1rem;">
      <!-- Left Side: Operation Cards (one per discovered workflow + History + Guide) -->
      <div class="column is-two-thirds">
        <div class="is-flex" style="flex-direction: column; gap: 1.5rem;">
          <p v-if="!availableWorkflows.length" class="notification is-warning">
            No workflows discovered. Check the Caldera log for plugin discovery errors.
          </p>

          <!-- One card per discovered workflow -->
          <div
            v-for="wf in availableWorkflows"
            :key="wf.id"
            class="box"
            style="display: flex; flex-direction: column; justify-content: space-between;"
          >
            <div style="flex-grow: 1;">
              <h3 class="title is-5">{{ wf.display_name }}</h3>
              <p v-if="wf.description">{{ wf.description }}</p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-primary" @click="setSelectedPath(wf.id)">
                Start {{ wf.display_name }} Session
              </button>
            </div>
          </div>

          <!-- CTI Ingest (raw → STIX) -->
          <div class="box" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="flex-grow: 1;">
              <h3 class="title is-5">Upload CTI</h3>
              <p>
                Ingest raw Cyber Threat Intelligence (HTML, PDF, plaintext) and run the
                MCP CTI pipeline: STIX 2.1 extraction. The structured output
                is what the model uses to plan operations.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-primary" @click="setSelectedPath('cti')">
                Start CTI Ingest
              </button>
            </div>
          </div>

          <!-- History (always on) -->
          <div class="box" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="flex-grow: 1;">
              <h3 class="title is-5">Run History</h3>
              <p>
                View and search all previous MCP runs with full chain of thought and execution details.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-info" @click="setSelectedPath('history')">
                View History
              </button>
            </div>
          </div>

          <!-- Extension Guide (always on) -->
          <div class="box" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="flex-grow: 1;">
              <h3 class="title is-5">Extend & Customize</h3>
              <p>
                Learn how to add a new MCP server, workflow, or capability from your own plugin.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-warning" @click="setSelectedPath('guide')">
                View Guide
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Side: Global Model Configuration (Pinned) -->
      <div class="column is-one-third">
          <div class="box" style="position: sticky; top: 1rem;">
            <h3 class="title is-5 has-text-primary mb-4">Global Model Config</h3>

          <div class="field">
            <label class="label">Endpoint Profile</label>
            <div class="control">
              <div class="select is-fullwidth">
                <select v-model="selectedEndpointProfileName" @change="applySelectedEndpointProfile">
                  <option value="">Manual settings</option>
                  <option
                    v-for="profile in endpointProfiles"
                    :key="profile.name"
                    :value="profile.name"
                  >
                    {{ profile.name }}
                  </option>
                </select>
              </div>
            </div>
          </div>

          <div class="field has-addons">
            <div class="control is-expanded">
              <input
                class="input"
                type="text"
                v-model="endpointProfileDraftName"
                placeholder="Profile name"
              />
            </div>
            <div class="control">
              <button class="button is-primary" type="button" @click="saveEndpointProfile">
                Save
              </button>
            </div>
            <div class="control">
              <button
                class="button is-light"
                type="button"
                @click="deleteSelectedEndpointProfile"
                :disabled="!selectedEndpointProfileName"
              >
                Delete
              </button>
            </div>
          </div>

          <div class="field">
            <label class="label">Model</label>
            <div class="control">
              <input
                class="input"
                type="text"
                v-model="globalConfig.modelName"
                placeholder="e.g., provider/model-name"
              />
            </div>
          </div>

          <div class="field">
            <label class="label">Temperature</label>
            <div class="control">
              <input
                class="input"
                type="number"
                v-model.number="globalConfig.temperature"
                step="0.1"
                min="0.1"
                max="1"
              />
            </div>
          </div>

          <div class="field">
            <label class="label">API Base</label>
            <div class="control">
              <input
                class="input"
                type="text"
                v-model="globalConfig.apiBase"
                placeholder="https://api.example.com/v1"
              />
            </div>
          </div>

          <div class="field">
            <label class="label">API Key</label>
            <div class="control">
              <input
                class="input"
                type="password"
                v-model="globalConfig.apiKey"
                placeholder="Enter API key"
              />
            </div>
          </div>

          <div class="field">
            <label class="checkbox">
              <input type="checkbox" v-model="globalConfig.sslVerify" />
              Verify TLS certificates
            </label>
          </div>

          <div class="field">
            <label class="label">Max Tool Calls</label>
            <div class="control">
              <input
                class="input"
                type="number"
                v-model.number="globalConfig.maxToolCalls"
                min="1"
                step="1"
              />
            </div>
          </div>

          <div class="field">
            <label class="label">Max Tokens</label>
            <div class="control">
              <input
                class="input"
                type="number"
                v-model.number="globalConfig.maxTokens"
                min="1000"
                step="1000"
              />
            </div>
          </div>

          <p class="is-size-7 has-text-grey-light">
            Server toggles and capability settings (e.g. RAG file picker)
            live inside each workflow's session page, scoped to what that
            workflow can actually use.
          </p>
        </div>
      </div>
    </div>

    <!-- Workflow session pages: routed dynamically by workflow_id. -->
    <component
      v-if="activeWorkflow"
      :is="resolveWorkflowComponent(activeWorkflow)"
      :workflow="activeWorkflow"
      :capabilities="availableCapabilities"
      @back="setSelectedPath(null)"
    />
    <McpHistory v-if="selectedPath === 'history'" @back="setSelectedPath(null)" />
    <McpCti v-if="selectedPath === 'cti'" @back="setSelectedPath(null)" />

    <!-- Embedded Extension Guide -->
    <div v-if="selectedPath === 'guide'" class="is-flex is-justify-content-center" style="width: 100%;">
      <div style="width: 85%;">
        <div class="box">
          <div class="is-flex is-align-items-center is-justify-content-space-between mb-4">
            <h2 class="title is-3 has-text-primary mb-0">MCP - Extend and Customize</h2>
            <button class="button is-light" @click="setSelectedPath(null)">
              ← Back to Main
            </button>
          </div>

          <div>
            <p class="subtitle is-5" style="color: #f5f5f5;">
              Guide for adding custom MCP use cases and extending the framework
            </p>

            <hr />

            <section class="mb-6">
              <h3 class="title is-4 has-text-light">Overview</h3>
              <p style="color: #f5f5f5;">
                This guide walks you through creating a new MCP use case similar to the existing
                <strong>LLM Ability Factory</strong> and <strong>LLM Operation Planner</strong>.
                Follow the steps below and use the templates provided to get started quickly.
              </p>
            </section>

            <section class="mb-6">
              <h3 class="title is-4 has-text-light">Quick Start Steps</h3>
              <p style="color: #f5f5f5;" class="mb-3">
                The MCP plugin discovers extensions at boot from any sibling
                Caldera plugin. Drop the files below at your plugin root and
                they appear automatically after a Caldera restart. No edits
                to the MCP plugin itself are required.
              </p>
              <div class="box" style="background-color: #4a4a4a;">
                <ol class="has-text-light" style="margin-left: 1.5rem;">
                  <li class="mb-2"><strong>MCP server</strong> &mdash; <code>plugins/&lt;name&gt;/mcp_server.py</code> with a top-level <code>MCP_METADATA = {...}</code> literal and one or more <code>@mcp.tool()</code> functions imported from <code>plugins/&lt;name&gt;/mcp/tools/</code>.</li>
                  <li class="mb-2"><strong>Workflow registration (optional)</strong> &mdash; <code>plugins/&lt;name&gt;/mcp/workflows.py</code> exposing <code>WORKFLOWS = [Workflow(...)]</code>. Each workflow declares its DSPy signature, required and optional MCP servers, and which capabilities it accepts.</li>
                  <li class="mb-2"><strong>Capability registration (optional)</strong> &mdash; <code>plugins/&lt;name&gt;/mcp/capabilities.py</code> exposing <code>CAPABILITIES = [Capability(...)]</code> for context modifiers any workflow can opt into.</li>
                  <li class="mb-2"><strong>Plan validator (optional)</strong> &mdash; <code>plugins/&lt;name&gt;/mcp/translator.py</code> with a <code>validate_plan()</code> function for two-phase plan-then-execute workflows.</li>
                  <li class="mb-2"><strong>Vue session page (optional)</strong> &mdash; <code>plugins/&lt;name&gt;/gui/views/&lt;component&gt;.vue</code>, referenced by name from your Workflow's <code>ui_component</code> field.</li>
                </ol>
              </div>
            </section>

            <section class="mb-6">
              <h3 class="title is-4 has-text-light">Example Use Cases</h3>
              <div class="columns">
                <div class="column">
                  <div class="box" style="background-color: #4a4a4a; border-left: 4px solid #3273dc;">
                    <h5 class="title is-6 has-text-light">Threat Hunter</h5>
                    <p class="is-size-7 has-text-light">
                      Analyzes adversary profile data to identify potential threats and suggests detection rules.
                    </p>
                  </div>
                </div>
                <div class="column">
                  <div class="box" style="background-color: #4a4a4a; border-left: 4px solid #209cee;">
                    <h5 class="title is-6 has-text-light">Operation Optimizer</h5>
                    <p class="is-size-7 has-text-light">
                      Reviews completed operations and suggests optimizations for future runs.
                    </p>
                  </div>
                </div>
                <div class="column">
                  <div class="box" style="background-color: #4a4a4a; border-left: 4px solid #ffdd57;">
                    <h5 class="title is-6 has-text-light">Campaign Builder</h5>
                    <p class="is-size-7 has-text-light">
                      Creates multi-stage adversary campaigns based on threat actor profiles.
                    </p>
                  </div>
                </div>
              </div>
            </section>

            <section class="mb-6">
              <h3 class="title is-4 has-text-light">Templates</h3>

              <h4 class="title is-5 mt-5 has-text-light">Basic MCP Client Template</h4>
              <p class="mb-3" style="color: #f5f5f5;">Create <code>app/mcp_custom_client.py</code>:</p>
              <pre class="p-4" style="background-color: #4a4a4a; border: 1px solid #363636; border-radius: 4px; overflow-x: auto; font-size: 0.85em; color: #f5f5f5;" v-pre><code>import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mlflow
import asyncio
import os
import sys

class DSPyCustomClient(dspy.Signature):
    """You are a [describe your role].
    You have access to Caldera API tools via MCP to [describe capabilities].
    """
    user_request: str = dspy.InputField()
    result: str = dspy.OutputField(desc="[Description of expected output]")

def get_env(lm_settings=None):
    """Prepare environment variables for MCP subprocess."""
    env = os.environ.copy()
    if lm_settings:
        env['DSPY_MODEL'] = str(lm_settings.get('model') or 'gpt-4o')
        env['DSPY_API_KEY'] = str(lm_settings.get('api_key') or '')
        env['DSPY_TEMPERATURE'] = str(lm_settings.get('temperature') or 0.5)
        env['DSPY_MAX_TOKENS'] = str(lm_settings.get('max_tokens') or 10000)
    return env

async def run(prompt: str, lm_obj=None, rag_context=None, run_id=None):
    """Execute the DSPy workflow with MCP tools."""
    mlflow.set_tracking_uri("http://localhost:5000")
    mlflow.set_experiment("caldera-mcp-CUSTOM-client")

    with mlflow.start_run(run_id=run_id):
        mlflow.set_tag("stage", "initializing MCP session")

        # Configure LLM
        if lm_obj and lm_obj.get("api_key"):
            dspy.configure(lm=dspy.LM(
                model=lm_obj.get("model"),
                api_key=lm_obj.get("api_key"),
                temperature=lm_obj.get("temperature"),
                max_tokens=lm_obj.get("max_tokens")
            ))

        # Connect to MCP server
        server_params = StdioServerParameters(
            command="python",
            args=["-u", "plugins/mcp/app/mcp_server.py"],
            env=get_env(lm_obj)
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # List and convert MCP tools
                tools_list = await session.list_tools()
                mlflow.set_tag("stage", "listing tools")

                dspy_tools = [
                    dspy.Tool.from_mcp_tool(session, tool)
                    for tool in tools_list.tools
                ]

                # Execute ReAct pattern
                mlflow.set_tag("stage", "executing DSPy ReAct")
                agent = dspy.ReAct(DSPyCustomClient, tools=dspy_tools)
                result = await agent(user_request=prompt)

                mlflow.log_param("process_result", result.result)
                mlflow.set_tag("stage", "complete")

                return {"process_result": result.result}

if __name__ == "__main__":
    # Test the client
    asyncio.run(run("Your test prompt here"))</code></pre>

              <h4 class="title is-5 mt-6 has-text-light">Vue Page Template</h4>
              <p class="mb-3" style="color: #f5f5f5;">Add to <code>mcp.vue</code> in the landing page cards section:</p>
              <pre class="p-4" style="background-color: #4a4a4a; border: 1px solid #363636; border-radius: 4px; overflow-x: auto; font-size: 0.85em; color: #f5f5f5;" v-pre><code>&lt;!-- Custom Use Case Card --&gt;
&lt;div class="box" style="display: flex; flex-direction: column; justify-content: space-between;"&gt;
  &lt;div style="flex-grow: 1;"&gt;
    &lt;h3 class="title is-5"&gt;Custom Use Case&lt;/h3&gt;
    &lt;p&gt;
      [Description of what your custom use case does]
    &lt;/p&gt;
  &lt;/div&gt;
  &lt;div class="is-flex is-justify-content-flex-end mt-4"&gt;
    &lt;button class="button is-primary" @click="selectedPath = 'custom'"&gt;
      Start Custom Session
    &lt;/button&gt;
  &lt;/div&gt;
&lt;/div&gt;</code></pre>

              <p class="mb-3 mt-4" style="color: #f5f5f5;">Then add the custom page view after the other page sections:</p>
              <pre class="p-4" style="background-color: #4a4a4a; border: 1px solid #363636; border-radius: 4px; overflow-x: auto; font-size: 0.85em; color: #f5f5f5;" v-pre><code>&lt;!-- Custom Use Case Page --&gt;
&lt;div v-if="selectedPath === 'custom'" class="is-flex is-justify-content-center" style="width: 100%;"&gt;
  &lt;div style="width: 75%;"&gt;
    &lt;div class="box"&gt;
      &lt;div class="is-flex is-align-items-center is-justify-content-space-between mb-3"&gt;
        &lt;h2 class="title is-4 has-text-primary mb-0"&gt;Custom Use Case&lt;/h2&gt;
      &lt;/div&gt;

      &lt;div class="field"&gt;
        &lt;div class="control"&gt;
          &lt;textarea
            v-model="customInput"
            class="textarea"
            rows="4"
            placeholder="Enter your request..."
          &gt;&lt;/textarea&gt;
        &lt;/div&gt;
      &lt;/div&gt;

      &lt;div class="is-flex is-justify-content-space-between is-align-items-center mt-4"&gt;
        &lt;button class="button is-light is-small" @click="selectedPath = null"&gt;
          ← Back
        &lt;/button&gt;

        &lt;button class="button is-primary" @click="handleCustomSubmit" :disabled="!customInput || customLoading"&gt;
          &lt;span v-if="customLoading"&gt;Processing...&lt;/span&gt;
          &lt;span v-else&gt;Submit&lt;/span&gt;
        &lt;/button&gt;
      &lt;/div&gt;

      &lt;div v-if="customResult" class="notification is-success mt-4"&gt;
        {{ customResult }}
      &lt;/div&gt;
    &lt;/div&gt;
  &lt;/div&gt;
&lt;/div&gt;

&lt;!-- Add to script setup section: --&gt;
&lt;script setup&gt;
const customInput = ref('')
const customLoading = ref(false)
const customResult = ref('')

async function handleCustomSubmit() {
  customLoading.value = true
  customResult.value = ''

  try {
    const response = await fetch('/plugin/mcp/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: customInput.value,
        type: 'custom',  // Must match ExecuteStyle enum value
        config: {
          model: globalConfig.modelName,
          api_key: globalConfig.apiKey,
          temperature: globalConfig.temperature,
          max_tokens: globalConfig.maxTokens,
          max_tool_calls: globalConfig.maxToolCalls
        }
      })
    })

    const data = await response.json()
    customResult.value = data.process_result || 'Success!'
  } catch (error) {
    customResult.value = 'Error: ' + error.message
  } finally {
    customLoading.value = false
  }
}
&lt;/script&gt;</code></pre>

              <div class="box mt-5" style="background-color: #4a4a4a;">
                <p class="mb-2 has-text-light"><strong>Next Steps:</strong></p>
                <ol class="has-text-light" style="margin-left: 1.5rem;">
                  <li class="mb-2">Update <code>app/mcp_svc.py</code> to add <code>LLMcustom = "custom"</code> to the <code>ExecuteStyle</code> enum</li>
                  <li class="mb-2">Import and call your client in the service layer's <code>_run_execution()</code> method</li>
                  <li class="mb-2">Restart Caldera to test your new use case</li>
                </ol>
                <p class="mt-3 has-text-light">See <code>plugins/mcp/CLAUDE.md</code> for detailed architecture information.</p>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, provide, reactive, watch, onMounted, computed } from 'vue'
// Both built-in workflows render through the same chat-style component;
// per-workflow behaviour (system prompt, accepted capabilities, chat
// history opt-in) is driven entirely by the workflow's registration
// data, which the component reads off props.workflow.
import McpChatWorkflow from './chat/ChatWorkflow.vue'
import McpHistory from './mcp_history.vue'
import McpCti from './cti.vue'

const SELECTED_PATH_STORAGE_KEY = 'mcp_selected_path'
const SPECIAL_PATHS = new Set(['cti', 'history', 'guide'])

function loadSelectedPath() {
  try {
    return localStorage.getItem(SELECTED_PATH_STORAGE_KEY) || null
  } catch (e) {
    console.warn('[MCP] Failed to load saved selected path:', e)
  }
  return null
}

// selectedPath holds either a workflow id (e.g. "author", "plan_execute") or
// one of the always-on cards: "history", "guide", "cti".
const selectedPath = ref(loadSelectedPath())

function setSelectedPath(path) {
  selectedPath.value = path
}

function selectedPathExists(path) {
  if (!path) return true
  if (SPECIAL_PATHS.has(path)) return true
  return availableWorkflows.value.some(w => w.id === path)
}

const availableWorkflows = ref([])
const availableCapabilities = ref([])
const availableServers = ref([])

const LOCAL_STORAGE_KEY = 'mcp_global_config'
// Bumped when a stored field stops being safe to reuse. v2 drops a cached
// apiBase: the endpoint moved out of the repo into MCP_LLM_API_BASE, and a
// value saved before that outranks it on every request, silently routing to
// an endpoint the deployment no longer configures.
const CONFIG_SCHEMA_VERSION = 2

// localStorage is readable by anything on this origin, so keys live in memory
// for the session only. Matched by name at any depth: a fixed list missed
// embed_api_key and plan_api_key nested under capabilitySettings.
const SECRET_KEY_NAME = /api_?key/i

function stripSecrets(value) {
  if (Array.isArray(value)) return value.map(stripSecrets)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([k]) => !SECRET_KEY_NAME.test(k))
        .map(([k, v]) => [k, stripSecrets(v)]),
    )
  }
  return value
}

// Named endpoint profiles keep their apiBase: those are explicit user
// artifacts, applied deliberately. Only the ambient default is dropped.
function migrate(config) {
  if (config.schemaVersion === CONFIG_SCHEMA_VERSION) return config
  const { apiBase, ...rest } = config
  return { ...rest, schemaVersion: CONFIG_SCHEMA_VERSION }
}

function loadConfig() {
  try {
    const saved = localStorage.getItem(LOCAL_STORAGE_KEY)
    if (!saved) return null
    const parsed = migrate(stripSecrets(JSON.parse(saved)))
    const cleaned = JSON.stringify(parsed)
    // Rewrite now rather than waiting for the next save.
    if (cleaned !== saved) localStorage.setItem(LOCAL_STORAGE_KEY, cleaned)
    return parsed
  } catch (e) {
    console.warn('[MCP] Failed to load saved config:', e)
  }
  return null
}

function saveConfig(config) {
  try {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify({
      ...stripSecrets(config),
      schemaVersion: CONFIG_SCHEMA_VERSION,
    }))
  } catch (e) {
    console.warn('[MCP] Failed to save config:', e)
  }
}

// Global configuration shared with all child components.
//
// Holds LM credentials/limits (model, endpoint, temperature, api_key,
// max_tool_calls, max_tokens) plus per-workflow and per-capability state:
//
//   serversByWorkflow    { <workflow_id>: [server_id, ...] }
//   capabilitiesByWorkflow { <workflow_id>: [capability_id, ...] }
//   capabilitySettings   { <capability_id>: { ...settings... } }
//
// RAG-specific fields (topk, embed_model) live under capabilitySettings.rag,
// not in the global LM config, since they belong to the RAG capability and
// are settable per workflow run.
const savedConfig = loadConfig()
const LEGACY_CHAT_MODEL_DEFAULTS = new Set([
  'openai/nemotron-3-super',
  'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
])
const globalConfig = reactive({
  modelName: savedConfig?.modelName || '',
  temperature: savedConfig?.temperature,
  apiBase: savedConfig?.apiBase || '',
  apiKey: savedConfig?.apiKey || '',
  sslVerify: savedConfig?.sslVerify,
  maxToolCalls: savedConfig?.maxToolCalls,
  maxTokens: savedConfig?.maxTokens,
  serversByWorkflow: savedConfig?.serversByWorkflow || {},
  capabilitiesByWorkflow: savedConfig?.capabilitiesByWorkflow || {},
  capabilitySettings: savedConfig?.capabilitySettings || {},
  endpointProfiles: Array.isArray(savedConfig?.endpointProfiles)
    ? savedConfig.endpointProfiles
    : [],
  selectedEndpointProfile: savedConfig?.selectedEndpointProfile || '',
})

const endpointProfileDraftName = ref(globalConfig.selectedEndpointProfile || '')
const endpointProfiles = computed(() => {
  if (!Array.isArray(globalConfig.endpointProfiles)) globalConfig.endpointProfiles = []
  return globalConfig.endpointProfiles
})
const selectedEndpointProfileName = computed({
  get: () => globalConfig.selectedEndpointProfile || '',
  set: (value) => {
    globalConfig.selectedEndpointProfile = value || ''
    if (value) endpointProfileDraftName.value = value
  },
})

function trimmedProfileName(value) {
  return String(value || '').trim()
}

function currentEndpointProfile(name) {
  return {
    name,
    modelName: globalConfig.modelName || '',
    temperature: globalConfig.temperature,
    apiBase: globalConfig.apiBase || '',
    apiKey: globalConfig.apiKey || '',
    sslVerify: globalConfig.sslVerify ?? true,
    maxToolCalls: globalConfig.maxToolCalls,
    maxTokens: globalConfig.maxTokens,
  }
}

function applyEndpointProfile(profile) {
  if (!profile) return
  globalConfig.modelName = profile.modelName || profile.model || ''
  globalConfig.temperature = profile.temperature
  globalConfig.apiBase = profile.apiBase || profile.api_base || ''
  globalConfig.apiKey = profile.apiKey || profile.api_key || ''
  globalConfig.sslVerify = profile.sslVerify ?? profile.ssl_verify ?? true
  globalConfig.maxToolCalls = profile.maxToolCalls ?? profile.max_tool_calls
  globalConfig.maxTokens = profile.maxTokens ?? profile.max_tokens
  endpointProfileDraftName.value = profile.name || ''
}

function applySelectedEndpointProfile() {
  const profile = endpointProfiles.value.find(p => p.name === selectedEndpointProfileName.value)
  if (profile) applyEndpointProfile(profile)
}

function saveEndpointProfile() {
  const name = trimmedProfileName(endpointProfileDraftName.value || selectedEndpointProfileName.value)
  if (!name) return
  const profile = currentEndpointProfile(name)
  const profiles = endpointProfiles.value.filter(p => p.name !== name)
  globalConfig.endpointProfiles = [...profiles, profile].sort((a, b) =>
    a.name.localeCompare(b.name)
  )
  selectedEndpointProfileName.value = name
}

function deleteSelectedEndpointProfile() {
  const name = selectedEndpointProfileName.value
  if (!name) return
  globalConfig.endpointProfiles = endpointProfiles.value.filter(p => p.name !== name)
  selectedEndpointProfileName.value = ''
}

function applyServerDefaults(d) {
  // Only fill fields the user hasn't already set.
  if (!globalConfig.modelName || LEGACY_CHAT_MODEL_DEFAULTS.has(globalConfig.modelName)) {
    globalConfig.modelName = d.model || ''
  }
  if (!globalConfig.apiBase)              globalConfig.apiBase       = d.api_base || ''
  if (globalConfig.sslVerify == null)     globalConfig.sslVerify     = d.ssl_verify ?? true
  if (globalConfig.temperature   == null) globalConfig.temperature   = d.temperature
  if (!globalConfig.maxToolCalls)         globalConfig.maxToolCalls  = d.max_tool_calls
  if (!globalConfig.maxTokens)            globalConfig.maxTokens     = d.max_tokens
  // Seed RAG capability defaults from the backend the first time around.
  if (!globalConfig.capabilitySettings.rag) globalConfig.capabilitySettings.rag = {}
  const rag = globalConfig.capabilitySettings.rag
  if (!rag.embed_model) rag.embed_model = d.rag_embed_model || ''
  if (rag.topk == null) rag.topk = d.rag_topk
}

// Resolve which Vue component renders a given workflow's session page.
// Built-in workflows ship with the MCP plugin and currently all use the
// same chat-style component; external plugins can supply their own via
// workflow.ui_component, which the magma bundler resolves relative to
// the plugin's gui/views/ directory.
const _BUILTIN_COMPONENTS = {
  'author.vue': McpChatWorkflow,
  'plan_execute.vue': McpChatWorkflow,
}

function resolveWorkflowComponent(wf) {
  return _BUILTIN_COMPONENTS[wf.ui_component] || McpChatWorkflow
}

const activeWorkflow = computed(() =>
  availableWorkflows.value.find(w => w.id === selectedPath.value) || null
)

onMounted(async () => {
  // Backend-driven defaults so the UI never duplicates yaml values.
  try {
    const resp = await fetch('/plugin/mcp/defaults')
    if (resp.ok) applyServerDefaults(await resp.json())
  } catch (e) {
    console.warn('[MCP] Failed to fetch /plugin/mcp/defaults:', e)
  }

  // Discover workflows, capabilities, and servers in parallel.
  try {
    const [wfResp, capResp, srvResp] = await Promise.all([
      fetch('/plugin/mcp/workflows'),
      fetch('/plugin/mcp/capabilities'),
      fetch('/plugin/mcp/servers'),
    ])
    const wfData = wfResp.ok ? await wfResp.json() : { workflows: [] }
    const capData = capResp.ok ? await capResp.json() : { capabilities: [] }
    const srvData = srvResp.ok ? await srvResp.json() : { servers: [] }
    availableWorkflows.value = wfData.workflows || []
    availableCapabilities.value = capData.capabilities || []
    availableServers.value = srvData.servers || []

    if (!selectedPathExists(selectedPath.value)) {
      setSelectedPath(null)
    }

    // Seed each workflow's default server toggles when no saved state exists.
    for (const wf of availableWorkflows.value) {
      if (globalConfig.serversByWorkflow[wf.id] === undefined) {
        // Default to required + any optional servers marked default_enabled
        // by their server registration.
        const defaultsByServer = Object.fromEntries(
          availableServers.value.map(s => [s.name, !!s.default_enabled])
        )
        const defaults = [
          ...wf.required_servers,
          ...wf.optional_servers.filter(s => defaultsByServer[s]),
        ]
        globalConfig.serversByWorkflow[wf.id] = [...new Set(defaults)]
      } else {
        // Drop any saved server names that no longer exist or are no longer
        // in this workflow's allowed scope.
        const allowed = new Set([...wf.required_servers, ...wf.optional_servers])
        globalConfig.serversByWorkflow[wf.id] =
          globalConfig.serversByWorkflow[wf.id].filter(n => allowed.has(n))
        // Required servers are always on regardless of what was saved.
        for (const req of wf.required_servers) {
          if (!globalConfig.serversByWorkflow[wf.id].includes(req)) {
            globalConfig.serversByWorkflow[wf.id].push(req)
          }
        }
      }
      if (globalConfig.capabilitiesByWorkflow[wf.id] === undefined) {
        globalConfig.capabilitiesByWorkflow[wf.id] = []
      } else {
        const allowedCaps = new Set(wf.accepted_capabilities)
        globalConfig.capabilitiesByWorkflow[wf.id] =
          globalConfig.capabilitiesByWorkflow[wf.id].filter(c => allowedCaps.has(c))
      }
    }
  } catch (e) {
    console.warn('[MCP] Failed to fetch workflow/capability/server registries:', e)
  }
})

watch(globalConfig, (newConfig) => {
  saveConfig(newConfig)
}, { deep: true })

watch(selectedPath, (path) => {
  try {
    if (path) localStorage.setItem(SELECTED_PATH_STORAGE_KEY, path)
    else localStorage.removeItem(SELECTED_PATH_STORAGE_KEY)
  } catch (e) {
    console.warn('[MCP] Failed to save selected path:', e)
  }
})

// Provide the shared config + registries to child workflow components.
provide('mcpGlobalConfig', globalConfig)
provide('mcpAvailableServers', availableServers)
provide('mcpAvailableCapabilities', availableCapabilities)
</script>
