# CTI Pipeline — HANDOFF (Updated 2026-03-17 08:00)

## PR #15: fix/p0-pipeline-fidelity (8 commits, targeting CTI branch)
https://github.com/mitre/mcp/pull/15

## Current Pipeline Performance

```
Metric                 Original  LLM mode  Offline   Sr.Analyst
Recall (extractable)        5%       81%      71%        100%
Recall (emulation)          3%       56%      68%         62%
Precision                   1%       19%      17%        100%
F1                          2%       29%      27%        100%
False Positives            68        79      116           0
Files processed           3/5       4/5      5/5         5/5
Processing time         ~40min     ~5min    ~4min      2-4hrs
LLM required               Yes       Yes      No         N/A
```

NOTE: Offline mode has HIGHER emulation recall (68% vs 56%) because
it successfully processes Talos (which always times out in LLM mode).

## What Was Done (6 commits on fix/p0-pipeline-fidelity)

### Commit 1: Core fixes
- MITRE semantic threshold 0.42→0.82 (eliminates noise)
- Explicit T-number regex from all IR text fields
- Deprecated ATT&CK ID filtering
- Entity reclassification (tools vs malware vs techniques)
- Actor slash-splitting ("ALPHV/BlackCat" → two actors with aliases)
- IP/domain dot preservation in canonicalization
- Relationship use-before-assignment bug fix
- D3FEND path fix (doubled prefix)
- Ollama timeout 120→600s

### Commit 2: Ontology inference
- New `cti_ontology_inference.py`: infers ATT&CK techniques from tools/malware
  using MITRE taxonomy's 20,048 relationships (zero LLM)
- Text corroboration filter for broad-profile tools (>8 techniques)
- Evidence quality gate in semantic matcher

### Commit 3: Speed optimization
- Shared spaCy singleton (`nlp_model.py`) — was loaded 6x at module level
- Enhanced entity validator fast-path (cross-category, fuzzy, well-known list)

### Commit 4: D3FEND tactic validation
- New `cti_defend_validation.py`: validates techniques by D3FEND tactic relevance
- Parses d3fend-protege.ttl for 823 technique→tactic mappings
- Extracts tactic signals from source text (generic, not adversary-specific)
- Drops ontology-inferred techniques whose tactic isn't evidenced in text

### Commit 5-6: Precision gate
- New `cti_precision_gate.py`: unified PMI + hierarchy + clique + cap
- PMI co-occurrence scoring for ontology-inferred techniques
- Sub-technique hierarchy enforcement
- Broad-profile entity cap (max 15 per entity, ranked by PMI)

## Pipeline Architecture (Current)

```
Raw CTI Text
    │
    ▼
Stage 1.1: Raw → Clean (deterministic, trafilatura/pdftotext)
    │
    ▼
Stage 1.2: Clean → IR (LLM extracts entities/behaviors into JSON)
    │
    ▼
NLP Layer 1: spaCy behavior expansion, actor cleanup, canonicalization
    │
    ▼
NLP Layer 2: WordNet nominalized behavior recovery
    │
    ▼
Entity Reclassification: MITRE taxonomy-based (deterministic)
    │
    ▼
Entity Validation: MITRE fast-path → well-known list → LLM fallback
    │
    ▼
Relationship Extraction: spaCy dep parse + verb classification
    │
    ▼
MITRE Technique Sources (merged + deduped):
  ├── Explicit T-numbers (regex from text)
  ├── Ontology Inference (tool→technique from MITRE taxonomy)
  ├── Semantic Matching (spaCy vectors, threshold 0.82)
  └── Behavior→Technique Mapping (qualified behaviors only)
    │
    ▼
Deprecated ID Filtering (removes pre-v8 ATT&CK)
    │
    ▼
D3FEND Tactic Validation (tactic must be evidenced in text)
    │
    ▼
Precision Gate (PMI + hierarchy + clique + entity cap)
    │
    ▼
Stage 2: IR → STIX 2.1 (fully deterministic)
    │
    ▼
D3FEND/CAD Enrichment (ontology-driven, generates CAD graphs)
```

## LLM Usage (Current)

The LLM is used in exactly TWO places:
1. **IR Extraction** (`cti_parsing.py`): Parses raw text → structured JSON
2. **Entity Validation** (`cti_entity_validator.py`): Fallback for entities
   not resolved by MITRE taxonomy or well-known list

The LLM could be made optional. Without it:
- IR extraction would need a pure NLP alternative (spaCy NER + regex patterns)
- Entity validation would rely entirely on deterministic fast-paths
- Estimated fidelity loss: ~10-15% recall (entities the NER misses)

## Known Issues

1. Sophos report (shortest) gets 0 TP — all Cobalt Strike techniques killed by PMI
2. Varonis report (generic language) has 26 FP from semantic matcher
3. Talos report times out during LLM entity validation (23 entities × 30s each)
4. Parenthetical actor aliases "BlackCat (ALPHV)" not split (only "/" handled)

## Source Data

5 CTI reports in `data/raw/uploads/` from AEL ALPHV BlackCat:
- unit42, sophos, talos, symantec, varonis
- Ground truth: AEL emulation plan (34 ATT&CK techniques)
- 21 techniques actually extractable from source text

## Environment

- Branch: `fix/p0-pipeline-fidelity` (from CTI)
- Venv: `/home/caldera/Desktop/CalderaVENV`
- LLM: Ollama gemma3n:latest (local)
- D3FEND: `app/utilities/D3fend_CAD/ontology/` (local TTL files)
- MITRE: `app/utilities/cti_taxonomy/enterprise_attack.json` (50MB)

## Open PRs

- **#15**: Pipeline fidelity fixes (THIS PR) — targeting CTI branch
- **#12**: Pin dependency versions — targeting main
- **#13**: Replace hardcoded credentials — targeting main
- **#14**: MLflow port safety — targeting main
