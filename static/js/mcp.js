/*
  Place any additional functions (non-Alpine specific) here.
*/
import { reactive } from 'vue'

export const mcpConfig = reactive({
  // LLM
  provider: null,
  model: null,
  api_key: null,
  api_base: null,

  temperature: 0.0,
  top_p: 1.0,
  max_tokens: 4000,
  max_tool_calls: 12,
  timeout: 120,

  offline: false,
  use_mock: false,

  // RAG
  rag_embed_model: null,
  rag_top_k: 5
})
