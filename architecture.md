DSpy -> LiteLLM (MITRE AIP LLM) -> Uses a ReACT pattern -> AI Agent for Reasoning Loop
- MCP Server -> API / Tool Calling Layer
- RAG -> Context Augmentation Layer (Where CTI would go)
- MLFlow -> Thoughts and Reasoning Obserability

Supporting N Caldera Plugins
-> MCP Plugin searches through every CALDERA Plugin to search for MCP Server
-> MCP Plugin deploys Plugin* server
-> Has tooling + API Routes for context and tool calls
<-> Powering ReACT and DSpy reasoning Loops


Caldera Core
-> MCP PLugin -> Look for a MCP Server -> Operations / ADversary / Abilities 
-> Range -> MCP Server -> API Endpoint with Swagger Docs
-> Plugin / N - MCP