# CTI Pipeline — HANDOFF (Updated 2026-03-17 16:00)

## Open PRs
- **PR #15**: fix/p0-pipeline-fidelity → CTI (20 commits) — deterministic pipeline
- **PR #16**: feature/llm-validation → CTI (10 commits) — LLM validation + combined mode

## Final Fidelity (6 sources: 5 BlackCat + 1 Russian APT)

```
                    Original   Without LLM   With LLM    Sr Analyst
TTP Recall              5%         65%          60%         100%
TTP Precision           1%         11%          14%         100%
Rel Recall              0%         20%          83%         100%
Actor Recall            0%         80%          86%         100%
Speed/file           ~8min        ~13s         ~54s       30-60min
LLM Required           Yes          No       Optional        N/A
```

## Architecture
Offline IR (always) → LLM IR merge (optional) → NLP enrichment
→ Entity reclassification → Dep-parse relationships
→ MITRE techniques (explicit + ontology + semantic)
→ D3FEND tactic filter → Keyword evidence filter → Precision gate
→ LLM technique validation (optional) → LLM relationship discovery (optional)
→ STIX 2.1 output → D3FEND/CAD enrichment

## What We Learned About Precision
- Deterministic filters (D3FEND, PMI, keywords) max out at ~14% TTP precision
- The ceiling is structural: mapping NL behaviors to abstract technique categories
  requires semantic understanding — deterministic methods can't bridge that gap
- LLM validation is the only lever that does what an analyst does (reads + decides)
- Next step: tune LLM denial threshold (deny only with high confidence)

## MITRE AIP Connection
SSH tunnel: `ssh -R 8443:models.k8s.aip.mitre.org:443 -R 8444:gitlab.mitre.org:443 caldera@192.168.1.185 -N`
Model: Devstral (24B), sub-second structured JSON responses
Config: plugins/mcp/conf/local.yml (gitignored)

## Key Files (PR #16)
- `cti_llm_validation.py` — quote-verified technique/relationship validation
- `cti_relation_extractor.py` — dep-parse with compound/conjunct/passive handling
- `cti_offline_ir.py` — MITRE taxonomy + spaCy NER extraction (no LLM)
- `cti_ontology_inference.py` — tool→technique from 20K MITRE relationships
- `cti_defend_validation.py` — D3FEND tactic + keyword evidence filtering
- `cti_precision_gate.py` — PMI + hierarchy + clique + entity cap
- `cti_stix_merge.py` — multi-source STIX merge with provenance
- `cti_stix_builders.py` — STIX 2.1 compliant SDO/SRO construction
- `tests/test_relation_extractor.py` — 18 unit tests across 10 threat actors
