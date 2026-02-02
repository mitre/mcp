<!-- ============================================================
     MCP EXTENSION GUIDE
     ============================================================ -->
<template>
  <div class="is-flex is-justify-content-center" style="width: 100%;">
    <div style="width: 95%; max-width: 1400px;">

      <div class="box">
        <!-- Header -->
        <div class="is-flex is-align-items-center is-justify-content-space-between mb-4">
          <h2 class="title is-3 has-text-primary mb-0">
            MCP – Extend and Customize
          </h2>
          <button
            class="button is-light is-small"
            @click="emit('back')"
          >
            ← Back
          </button>
        </div>

        <!-- Content -->
        <div class="content">

          <p class="subtitle is-5">
            Guide for adding custom MCP use cases and extending the framework
          </p>

          <hr />

          <!-- Overview -->
          <section class="mb-6">
            <h3 class="title is-4">Overview</h3>
            <p>
              This guide walks you through creating a new MCP use case similar to the existing
              <strong>LLM Ability Factory</strong> and
              <strong>LLM Operation Planner</strong>.
              Follow the steps below and use the templates provided to get started quickly.
            </p>
          </section>

          <!-- Quick Start -->
          <section class="mb-6">
            <h3 class="title is-4">🚀 Quick Start Steps</h3>
            <p class="mb-3">
              <strong>Define Your Use Case:</strong>
              Determine what your extension will do
              (e.g., threat hunter, campaign builder).
            </p>

            <div class="notification has-background-grey-darker has-text-light">
              <ol style="margin-left: 1.5rem;">
                <li class="mb-2">
                  <strong>Create DSPy Client</strong> –
                  Build <code>app/mcp_&lt;name&gt;_client.py</code> with custom signatures
                </li>
                <li class="mb-2">
                  <strong>Add MCP Tools (Optional)</strong> –
                  Extend <code>app/mcp_server.py</code> with custom tools
                </li>
                <li class="mb-2">
                  <strong>Update Service Layer</strong> –
                  Add your use case to <code>ExecuteStyle</code> in <code>app/mcp_svc.py</code>
                </li>
                <li class="mb-2">
                  <strong>Create Vue Frontend</strong> –
                  Build UI component in <code>gui/views/</code>
                </li>
                <li class="mb-2">
                  <strong>Add Navigation</strong> –
                  Register component in <code>mcp.vue</code>
                </li>
              </ol>
            </div>
          </section>

          <!-- Example Use Cases -->
          <section class="mb-6">
            <h3 class="title is-4">Example Use Cases</h3>

            <div class="columns">
              <div class="column">
                <div class="notification" style="border-left: 4px solid #3273dc;">
                  <h5 class="title is-6">Threat Hunter</h5>
                  <p class="is-size-7">
                    Analyzes adversary profiles to identify threats and suggest detections.
                  </p>
                </div>
              </div>

              <div class="column">
                <div class="notification" style="border-left: 4px solid #209cee;">
                  <h5 class="title is-6">Operation Optimizer</h5>
                  <p class="is-size-7">
                    Reviews completed operations and recommends improvements.
                  </p>
                </div>
              </div>

              <div class="column">
                <div class="notification" style="border-left: 4px solid #ffdd57;">
                  <h5 class="title is-6">Campaign Builder</h5>
                  <p class="is-size-7">
                    Creates multi-stage campaigns from threat actor profiles.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <!-- Templates -->
          <section class="mb-6">
            <h3 class="title is-4">Templates</h3>

            <h4 class="title is-5 mt-5">Basic MCP Client Template</h4>
            <p>Create <code>app/mcp_custom_client.py</code>:</p>

            <pre><code>import dspy
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mlflow
import asyncio
import os

class DSPyCustomClient(dspy.Signature):
    """You are a custom MCP client."""
    user_request: str = dspy.InputField()
    result: str = dspy.OutputField()

async def run(prompt: str, lm_obj=None, run_id=None):
    mlflow.set_experiment("caldera-mcp-custom")

    with mlflow.start_run(run_id=run_id):
        dspy.configure(lm=dspy.LM(
            model=lm_obj.get("model"),
            api_key=lm_obj.get("api_key"),
            temperature=lm_obj.get("temperature"),
            max_tokens=lm_obj.get("max_tokens")
        ))

        server = StdioServerParameters(
            command="python",
            args=["-u", "plugins/mcp/app/mcp_server.py"]
        )

        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()

                agent = dspy.ReAct(DSPyCustomClient, tools=[
                    dspy.Tool.from_mcp_tool(session, t)
                    for t in tools.tools
                ])

                result = await agent(user_request=prompt)
                mlflow.log_param("process_result", result.result)
                return {"process_result": result.result}</code></pre>

            <h4 class="title is-5 mt-6">Vue Page Template</h4>
            <p>Add a card in <code>mcp.vue</code>:</p>

            <pre><code>&lt;div class="box"&gt;
  &lt;h3 class="title is-5"&gt;Custom Use Case&lt;/h3&gt;
  &lt;p&gt;Describe your custom MCP use case&lt;/p&gt;
  &lt;div class="is-flex is-justify-content-flex-end mt-4"&gt;
    &lt;button class="button is-primary" @click="selectedPath = 'custom'"&gt;
      Start Custom Session
    &lt;/button&gt;
  &lt;/div&gt;
&lt;/div&gt;</code></pre>

            <div class="notification mt-5">
              <p><strong>Next Steps:</strong></p>
              <ol style="margin-left: 1.5rem;">
                <li>Add your use case to <code>ExecuteStyle</code> enum</li>
                <li>Wire client execution in the service layer</li>
                <li>Restart Caldera and test</li>
              </ol>
              <p class="mt-3">
                See <code>plugins/mcp/CLAUDE.md</code> for architecture details.
              </p>
            </div>
          </section>

        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const emit = defineEmits(['back'])
</script>

<style scoped>
pre {
  white-space: pre-wrap;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco,
               Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.85rem;
}
</style>
