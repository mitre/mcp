# CTI Pipeline — HANDOFF (Updated 2026-03-17 14:00)

## Open PRs
- **PR #15**: fix/p0-pipeline-fidelity → CTI (20 commits) — deterministic improvements
- **PR #16**: feature/llm-validation → CTI (6 commits) — LLM validation layer

## Final Performance (Combined: Offline IR + LLM Merge + LLM Validation)

```
                    Original    PR#15       PR#16        Sr. Analyst
                    (broken)    (offline)   (combined)
TTP Recall              5%        65%          61%          100%
TTP Precision           1%        11%           9%          100%
Rel Recall              0%        22%          95%          100%
Rel Count             571         41          131            ~16
Time/file            ~8min       ~13s         ~56s        30-60min
LLM Required           Yes        No      Optional           N/A
STIX 2.1               No        Yes          Yes           N/A
D3FEND              Broken    Working      Working           N/A
```

## Architecture
```
Raw CTI → Clean text → OFFLINE IR (always, ~5s)
  → LLM IR merge (optional, additive, ~20s)
  → NLP enrichment → Entity reclassification
  → Dep-parse relationships
  → MITRE techniques (explicit + ontology + semantic)
  → D3FEND tactic validation → Precision gate
  → LLM technique validation (optional, confirms/denies)
  → LLM relationship discovery (optional, biggest win: 22%→95%)
  → STIX 2.1 output → D3FEND/CAD enrichment
```

## MITRE AIP Connection
SSH tunnel from user's Mac: `ssh -R 8443:models.k8s.aip.mitre.org:443 caldera@192.168.1.185 -N`
Model: Devstral (24B) — fast structured JSON, sub-second responses
