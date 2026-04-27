<template>
  <div class="content">
    <div v-if="!selectedPath">
      <h2 class="title is-3">Caldera MCP: AI-Powered Operations</h2>
      <hr />
    </div>

    <!-- Main Layout: Cards on Left, Config on Right -->
    <div v-if="!selectedPath" class="columns" style="margin: 0 1rem;">
      <!-- Left Side: Operation Cards -->
      <div class="column is-two-thirds">
        <div class="is-flex" style="flex-direction: column; gap: 1.5rem;">
          <!-- LLM Factory -->
          <div class="box" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="flex-grow: 1;">
              <h3 class="title is-5">LLM Ability Factory</h3>
              <p>
                AI creates new abilities and adversaries based on your descriptions. Best for creating specific capabilities.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-primary" @click="selectedPath = 'factory'">
                Start Factory Session
              </button>
            </div>
          </div>

          <!-- LLM Planner -->
          <div class="box" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="flex-grow: 1;">
              <h3 class="title is-5">LLM Operation Planner</h3>
              <p>
                AI plans and executes complete adversary operations. Best for comprehensive attack scenarios.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-primary" @click="selectedPath = 'planner'">
                Start Planner Session
              </button>
            </div>
          </div>

          <!-- History -->
          <div class="box" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="flex-grow: 1;">
              <h3 class="title is-5">Run History</h3>
              <p>
                View and search all previous MCP runs with full chain of thought and execution details.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-info" @click="selectedPath = 'history'">
                View History
              </button>
            </div>
          </div>

          <!-- Extension Guide -->
          <div class="box" style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="flex-grow: 1;">
              <h3 class="title is-5">Extend & Customize</h3>
              <p>
                Learn how to create custom MCP use cases and extend the framework with new capabilities.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button class="button is-warning" @click="selectedPath = 'guide'">
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
            <label class="label">Model</label>
            <div class="control">
              <input
                class="input"
                type="text"
                v-model="globalConfig.modelName"
                placeholder="e.g., openai/nemotron-3-super"
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

          <div class="field">
            <label class="label">Enabled MCP Servers</label>
            <div class="control" v-if="availableServers.length">
              <label
                v-for="srv in availableServers"
                :key="srv.name"
                class="checkbox is-block mb-1"
                :title="srv.description"
              >
                <input
                  type="checkbox"
                  :value="srv.name"
                  v-model="globalConfig.enabledServers"
                />
                {{ srv.display_name }}
                <span class="has-text-grey-light is-size-7">({{ srv.name }})</span>
              </label>
            </div>
            <p v-else class="help is-warning">No MCP servers discovered.</p>
          </div>

          <div class="field">
            <label class="label">RAG TopK</label>
            <div class="control">
              <input
                class="input"
                type="number"
                v-model.number="globalConfig.ragTopK"
                min="1"
                max="30"
                step="1"
              />
            </div>
          </div>

          <div class="field">
            <label class="label">RAG Embed Model</label>
            <div class="control">
              <input
                class="input"
                type="text"
                v-model="globalConfig.ragEmbedModel"
                placeholder="openai/text-embedding-3-small"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <McpPromptFactory v-if="selectedPath === 'factory'" @back="selectedPath = null" />
    <McpPromptPlanner v-if="selectedPath === 'planner'" @back="selectedPath = null" />
    <McpHistory v-if="selectedPath === 'history'" @back="selectedPath = null" />

    <!-- Embedded Extension Guide -->
    <div v-if="selectedPath === 'guide'" class="is-flex is-justify-content-center" style="width: 100%;">
      <div style="width: 85%;">
        <div class="box">
          <div class="is-flex is-align-items-center is-justify-content-space-between mb-4">
            <h2 class="title is-3 has-text-primary mb-0">MCP - Extend and Customize</h2>
            <button class="button is-light" @click="selectedPath = null">
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
              <h3 class="title is-4 has-text-light">🚀 Quick Start Steps</h3>
              <p style="color: #f5f5f5;" class="mb-3">
                <strong>Define Your Use Case:</strong> Determine what your extension will do (e.g., threat hunter, campaign builder)
              </p>
              <div class="box" style="background-color: #4a4a4a;">
                <ol class="has-text-light" style="margin-left: 1.5rem;">
                  <li class="mb-2"><strong>Create DSPy Client</strong> - Build <code>app/mcp_&lt;name&gt;_client.py</code> with custom signatures</li>
                  <li class="mb-2"><strong>Add MCP Tools (Optional)</strong> - Extend <code>app/mcp_server.py</code> with custom tools</li>
                  <li class="mb-2"><strong>Update Service Layer</strong> - Add your use case to <code>ExecuteStyle</code> enum in <code>app/mcp_svc.py</code></li>
                  <li class="mb-2"><strong>Create Vue Frontend</strong> - Build UI component in <code>gui/views/</code></li>
                  <li class="mb-2"><strong>Add Navigation</strong> - Register component in <code>mcp.vue</code></li>
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
import { ref, provide, reactive, watch, onMounted } from 'vue'
import McpPromptFactory from './local_mcp_ability_factory.vue'
import McpPromptPlanner from './public_mcp_ability_factory.vue'
import McpHistory from './mcp_history.vue'

const selectedPath = ref(null)
const availableServers = ref([])
const LOCAL_STORAGE_KEY = 'mcp_global_config'

// Load saved config from localStorage
function loadConfig() {
  try {
    const saved = localStorage.getItem(LOCAL_STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      console.log('[MCP] Loaded config from localStorage:', {
        modelName: parsed.modelName,
        temperature: parsed.temperature,
        hasApiKey: !!parsed.apiKey,
        apiKeyLength: parsed.apiKey?.length || 0,
        maxToolCalls: parsed.maxToolCalls,
        maxTokens: parsed.maxTokens,
        ragEmbedModel: parsed.ragEmbedModel,
        ragTopK: parsed.ragTopK
      })
      return parsed
    } else {
      console.log('[MCP] No saved config found in localStorage')
    }
  } catch (e) {
    console.warn('[MCP] Failed to load saved config:', e)
  }
  return null
}

// Save config to localStorage
function saveConfig(config) {
  try {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(config))
    console.log('[MCP] Saved config to localStorage:', {
      modelName: config.modelName,
      temperature: config.temperature,
      hasApiKey: !!config.apiKey,
      apiKeyLength: config.apiKey?.length || 0,
      maxToolCalls: config.maxToolCalls,
      maxTokens: config.maxTokens,
      ragEmbedModel: config.ragEmbedModel,
      ragTopK: config.ragTopK
    })
  } catch (e) {
    console.warn('[MCP] Failed to save config:', e)
  }
}

// Global configuration that will be shared with all child components
// Load from localStorage if available, otherwise use defaults
const savedConfig = loadConfig()
const globalConfig = reactive({
  modelName: savedConfig?.modelName || 'openai/nemotron-3-super',
  temperature: savedConfig?.temperature ?? 0.5,
  apiKey: savedConfig?.apiKey || '',
  maxToolCalls: savedConfig?.maxToolCalls || 5,
  maxTokens: savedConfig?.maxTokens || 10000,
  ragEmbedModel: savedConfig?.ragEmbedModel || 'openai/text-embedding-3-small',
  ragTopK: savedConfig?.ragTopK ?? 5,
  enabledServers: savedConfig?.enabledServers || []
})

// Discover MCP servers and reconcile against saved enabled list.
onMounted(async () => {
  try {
    const resp = await fetch('/plugin/mcp/servers')
    const data = await resp.json()
    availableServers.value = data.servers || []
    const known = new Set(availableServers.value.map(s => s.name))

    if (!savedConfig?.enabledServers) {
      // First load — default to whatever the registry marks default_enabled.
      globalConfig.enabledServers = availableServers.value
        .filter(s => s.default_enabled)
        .map(s => s.name)
    } else {
      // Drop any saved entries that no longer exist.
      globalConfig.enabledServers = globalConfig.enabledServers.filter(n => known.has(n))
    }
  } catch (e) {
    console.warn('[MCP] Failed to fetch /plugin/mcp/servers:', e)
  }
})

// Watch for changes and save to localStorage
watch(globalConfig, (newConfig) => {
  saveConfig(newConfig)
}, { deep: true })

// Provide the global config to all child components
provide('mcpGlobalConfig', globalConfig)
</script>
