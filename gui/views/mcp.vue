<template>
  <div class="content">

    <!-- =========================================================
         LANDING HEADER
         ========================================================= -->
    <div v-if="!selectedPath">
      <h2 class="title is-3">Caldera MCP: AI-Powered Operations</h2>
      <hr />
    </div>

    <!-- =========================================================
         LANDING PAGE (CARDS + GLOBAL MODEL CONFIG)
         ========================================================= -->
    <div
      v-if="!selectedPath"
      class="columns"
      style="margin: 0 1rem;"
    >
      <!-- ================= LEFT: ENTRY CARDS ================= -->
      <div class="column is-two-thirds">
        <div
          class="is-flex"
          style="flex-direction: column; gap: 1.5rem;"
        >

          <!-- Ability Factory -->
          <div class="box is-flex is-flex-direction-column is-justify-content-space-between">
            <div>
              <h3 class="title is-5">LLM Ability Factory</h3>
              <p>
                AI creates new abilities and adversaries based on your descriptions.
                Best for creating focused capabilities.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button
                class="button is-primary"
                @click="selectedPath = 'factory'"
              >
                Start Factory Session
              </button>
            </div>
          </div>

          <!-- Operation Planner -->
          <div class="box is-flex is-flex-direction-column is-justify-content-space-between">
            <div>
              <h3 class="title is-5">LLM Operation Planner</h3>
              <p>
                AI plans and executes complete adversary operations.
                Best for multi-stage attack scenarios.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button
                class="button is-primary"
                @click="selectedPath = 'planner'"
              >
                Start Planner Session
              </button>
            </div>
          </div>

          <!-- CTI Ingest -->
          <div class="box is-flex is-flex-direction-column is-justify-content-space-between">
            <div>
              <h3 class="title is-5">Upload CTI</h3>
              <p>
                Upload raw Cyber Threat Intelligence and convert it into structured
                STIX for RAG-powered planning and ability generation.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button
                class="button is-primary"
                @click="selectedPath = 'cti'"
              >
                Start CTI Ingest
              </button>
            </div>
          </div>

          <!-- Run History -->
          <div class="box is-flex is-flex-direction-column is-justify-content-space-between">
            <div>
              <h3 class="title is-5">Run History</h3>
              <p>
                View and search previous MCP runs with full execution details.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button
                class="button is-info"
                @click="selectedPath = 'history'"
              >
                View History
              </button>
            </div>
          </div>

          <!-- Extension Guide -->
          <div class="box is-flex is-flex-direction-column is-justify-content-space-between">
            <div>
              <h3 class="title is-5">Extend & Customize</h3>
              <p>
                Learn how to create custom MCP use cases and extend the framework.
              </p>
            </div>
            <div class="is-flex is-justify-content-flex-end mt-4">
              <button
                class="button is-warning"
                @click="selectedPath = 'guide'"
              >
                View Guide
              </button>
            </div>
          </div>

        </div>
      </div>

      <!-- ================= RIGHT: GLOBAL MODEL CONFIG ================= -->
      <div class="column is-one-third">
        <McpModelConfigPanel
          :backend-config="backendConfig"
          config-key="llm"
          @validity="isModelConfigValid = $event"
        />
      </div>
    </div>

    <!-- =========================================================
         SUB-PAGES
         ========================================================= -->
    <McpPromptFactory
      v-if="selectedPath === 'factory'"
      @back="selectedPath = null"
    />

    <McpPromptPlanner
      v-if="selectedPath === 'planner'"
      @back="selectedPath = null"
    />

    <McpHistory
      v-if="selectedPath === 'history'"
      @back="selectedPath = null"
    />

    <McpCti
      v-if="selectedPath === 'cti'"
      @back="selectedPath = null"
    />

    <McpGuide
      v-if="selectedPath === 'guide'"
      @back="selectedPath = null"
    />
  </div>
</template>

<script setup>
/* ============================================================
 * Imports
 * ============================================================ */
import { computed, onMounted, provide, ref } from 'vue'

import McpCti from './cti.vue'
import McpGuide from '../components/mcpGuide.vue'
import McpHistory from './mcp_history.vue'
import McpModelConfigPanel from '../components/modelSelector.vue'
import McpPromptFactory from './mcp_ability_factory.vue'
import McpPromptPlanner from './mcp_planner.vue'

/* ============================================================
 * Global Model Config State (Authoritative)
 * ============================================================ */
const backendConfig = ref(null)
const isModelConfigValid = ref(false)

/* ============================================================
 * Navigation State
 * ============================================================ */
const selectedPath = ref(null)

/* ============================================================
 * Provide Globals to Children
 * ============================================================ */
provide('isModelConfigValid', isModelConfigValid)

provide('mcpGlobalConfig', {
  config: computed(() => backendConfig.value ?? {})
})

/* ============================================================
 * Backend Config Loading
 * ============================================================ */
async function loadBackendConfig() {
  const res = await fetch('/plugin/mcp/get_config')
  if (!res.ok) {
    throw new Error('Failed to load MCP config')
  }

  const data = await res.json()
  const cfg = data?.config ?? data ?? {}

  backendConfig.value = cfg.llm ?? {}
}

/* ============================================================
 * Lifecycle
 * ============================================================ */
onMounted(loadBackendConfig)
</script>
