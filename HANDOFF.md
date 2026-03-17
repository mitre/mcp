# CTI Pipeline — HANDOFF (Updated 2026-03-17 10:00)

## PR #15: fix/p0-pipeline-fidelity (18 commits, targeting CTI branch)
https://github.com/mitre/mcp/pull/15

## Current Performance (Offline Mode, 5 Sources, Averaged)

```
Metric                 Original    Current    Senior Analyst
TTP Recall (extract)        5%       65%            100%
TTP Precision              1%       11%            100%
Actor Recall               0%       80%            100%
Rel Count               571         41              16
Rel Recall               N/A       22%            100%
Time/file              ~8min      ~44s          30-60min
LLM Required             Yes        No             N/A
```

## Relationship Extraction Progression
```
Version                  Rels  Rel-Recall  Actor-Recall
Original (cartesian)      571      N/A          0%
+Dep-parse extractor       37      17%          0%
+Default actor              37      17%          0%
+pobj subtree walk          42      17%          0%
+Frequency actor extract    41      22%         80%
```

## Key Files Changed (18 commits)
- `cti_relation_extractor.py` — NEW: dep-parse triple extraction
- `cti_offline_ir.py` — NEW: LLM-free IR extraction
- `cti_ontology_inference.py` — NEW: tool→technique from MITRE taxonomy
- `cti_defend_validation.py` — NEW: D3FEND tactic validation gate
- `cti_precision_gate.py` — NEW: PMI + hierarchy + clique + cap
- `cti_stix_merge.py` — NEW: multi-source STIX merge
- `cti_stix_builders.py` — STIX 2.1 compliance fixes
- `cti_entity_validator.py` — entity reclassification + fast-path
- `cti_linguistics.py` — threshold + evidence quality gate
- `cti_pipeline_stage1.py` — pipeline wiring for all above
- `cti_pipeline_stage2.py` — D3FEND path fix
- `nlp_model.py` — NEW: shared spaCy singleton
- `tests/test_relation_extractor.py` — 18 unit tests, 100% pass

## Environment
- Branch: `fix/p0-pipeline-fidelity` (from CTI)
- Venv: `/home/caldera/Desktop/CalderaVENV`
- Config: `conf/local.yml` (cti.offline: true/false)
