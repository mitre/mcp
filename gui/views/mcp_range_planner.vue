<!-- gui/views/mcp_range_planner.vue -->
<template>
  <div class="mcp-range-planner">
    <h2>LLM Range Planner</h2>

    <div class="mcp-section">
      <label for="prompt">Prompt</label>
      <textarea
        id="prompt"
        v-model="prompt"
        placeholder="e.g. Deploy a range that would allow me to execute the thief adversary."
      />
    </div>

    <div class="mcp-section">
      <!-- reuse the same model config panel the other views use -->
      <h3>Model Configuration</h3>
      <!-- inputs for model, api_key, temperature, max_tokens, max_tool_calls -->
      <!-- (bind to config.model, config.api_key, etc.) -->
    </div>

    <button :disabled="loading || !prompt" @click="executeRangePlanner">
      {{ loading ? "Submitting..." : "Execute Range Planner" }}
    </button>

    <div v-if="runId" class="mcp-section">
      <p>Run ID: {{ runId }}</p>
      <p>Status: {{ status.stage }} ({{ status.status }})</p>
      <p v-if="status.process_result">{{ status.process_result }}</p>
    </div>
  </div>
</template>

<script>
export default {
  name: "McpRangePlanner",
  data() {
    return {
      prompt: "",
      config: {
        model: "",
        api_key: "",
        temperature: 0.4,
        max_tokens: 1024,
        max_tool_calls: 5,
        // plus any RAG config if you want to reuse that
      },
      runId: null,
      status: {},
      loading: false,
      statusInterval: null,
    };
  },
  methods: {
    async executeRangePlanner() {
      this.loading = true;
      try {
        const resp = await fetch("/plugin/mcp/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: this.prompt,
            type: "range_planner", // critical: matches ExecuteStyle.RANGEplanner
            config: this.config,
          }),
        });
        const data = await resp.json();
        this.runId = data.run_id;
        this.startPollingStatus();
      } finally {
        this.loading = false;
      }
    },
    async pollStatus() {
      if (!this.runId) return;
      const resp = await fetch(`/plugin/mcp/status?run_id=${this.runId}`);
      const data = await resp.json();
      this.status = data;
      if (data.status === "FINISHED" || data.status === "FAILED" || data.stage === "complete" || data.stage === "error") {
        clearInterval(this.statusInterval);
        this.statusInterval = null;
      }
    },
    startPollingStatus() {
      if (this.statusInterval) clearInterval(this.statusInterval);
      this.statusInterval = setInterval(this.pollStatus, 2000);
    },
  },
  beforeDestroy() {
    if (this.statusInterval) clearInterval(this.statusInterval);
  },
};
</script>
