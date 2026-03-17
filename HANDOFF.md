# CTI Pipeline — HANDOFF (Updated 2026-03-17 12:00)

## Open PRs

### PR #15: fix/p0-pipeline-fidelity → CTI (20 commits) — READY FOR REVIEW
https://github.com/mitre/mcp/pull/15

All deterministic improvements. No LLM dependency.

### PR #16: feature/llm-validation → CTI (1 commit) — NEEDS REMOTE LLM
https://github.com/mitre/mcp/pull/16

Optional LLM validation layer. Blocked on remote LLM endpoint (local
gemma3n too slow for structured JSON validation prompts).

## Current Performance (PR #15, Offline Mode, 5 Sources)

```
Metric                 Original    PR #15     Delta   Sr Analyst
TTP Recall                   5%      65%     +60pp        100%
TTP Precision                1%      11%     +10pp        100%
Actor Recall                 0%      80%     +80pp        100%
Tool Recall                 29%      75%     +46pp        100%
Rel Recall                   0%      20%     +20pp        100%
Rel Count                  571       40      -531          ~16
Speed                    ~8min     ~13s*      97%      30-60min
LLM Required               Yes       No    Removed         N/A
STIX 2.1 Compliant          No      Yes     Fixed          N/A
D3FEND                  Broken  Working     Fixed          N/A
```
*13s avg per file after first (first file ~50s for cache build)

## PR #16 Expected Impact (pending remote LLM testing)
```
Metric                 PR #15    +LLM Val    Expected
TTP Precision             11%     40-60%     LLM removes FP techniques
Rel Recall                20%     40-50%     LLM discovers cross-sentence rels
Speed/file               ~13s     ~40s       +27s for validation calls
```

## Key Architecture

```
Raw CTI → Clean → IR (offline or LLM) → NLP → Entity Reclass
→ Dep-Parse Relationships → MITRE Techniques (explicit + ontology + semantic)
→ D3FEND Tactic Validation → Precision Gate → [LLM Validation (optional)]
→ STIX 2.1 → D3FEND/CAD Enrichment
```

LLM is used for:
- PR #15: nowhere (fully offline capable)
- PR #16: validation only (confirms/denies, never extracts)

## To Test PR #16

Configure remote LLM in conf/local.yml:
```yaml
cti:
  model: gpt-4o-mini  # or any fast model
  provider: openai
  api_key: "your-key"
  api_base: https://your-endpoint/v1
  offline: false
```

## Environment
- Branch PR#15: `fix/p0-pipeline-fidelity`
- Branch PR#16: `feature/llm-validation`
- Venv: `/home/caldera/Desktop/CalderaVENV`
