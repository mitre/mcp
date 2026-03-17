# CTI Pipeline Baseline Fidelity Report

**Date**: 2026-03-16
**Branch**: `CTI`
**Test Data**: ALPHV/BlackCat CTI reports from MITRE ATT&CK Evals AEL
**Ground Truth**: AEL Emulation Plan (34 ATT&CK techniques, 14 tools, BlackCat malware)
**LLM**: Ollama gemma3n:latest (local)
**Reports Processed**: 3 of 5 (Unit42 and Varonis failed due to Ollama crashes)

---

## Executive Summary

The pipeline produces structurally valid STIX bundles but has **critically low fidelity** for CTI-driven RAG:

| Metric | Score | Assessment |
|--------|-------|------------|
| ATT&CK Technique Recall | **3%** (1/34) | FAILING |
| ATT&CK Technique Precision | **1%** (1/69) | FAILING |
| Tool Recall | **29%** (4/14) | POOR |
| Malware Detection | Partial | BlackCat found, but 12 false positives |
| Actor Detection | Partial | BlackCat found, ALPHV missed |
| Relationship Extraction | **2 total** | FAILING |
| STIX Structural Validity | ~95% | ACCEPTABLE (2 x-cti-artifact warnings) |
| D3FEND Enrichment | 0% | BROKEN (path bug) |

**Verdict**: The STIX output is NOT usable for RAG in its current state. An analyst querying this bundle would get mostly noise.

---

## Detailed Findings

### 1. ATT&CK Technique Mapping (CRITICAL FAILURE)

**The single biggest problem.** The pipeline found 69 technique IDs but only 1 matches ground truth (T1555 - Credentials from Password Stores). The other 68 are false positives.

**Root Cause**: The MITRE matching layer (`cti_linguistics.py`) uses spaCy vector similarity to match free-text behavior phrases against technique descriptions. This produces **high-recall, near-zero-precision** matches because:
- Behavior phrases are too short/generic ("tools before encryption re", "collecting sensitive information using")
- The similarity threshold (0.79) is too low — it matches almost everything
- No disambiguation: a phrase like "collecting sensitive information" matches T1602 (SNMP MIB Dump), T1114 (Email Collection), and T1213 (Data from Information Repositories) equally
- Deprecated technique IDs are included (T1089, T1194, T1493)

**What should have matched (from source text)**:
- T1486 (Data Encrypted for Impact) — "ransomware", "encryption" mentioned repeatedly
- T1490 (Inhibit System Recovery) — "shadow copy deletion" explicitly described
- T1489 (Service Stop) — "terminates 47+ processes/services" explicitly stated
- T1021.001 (Remote Desktop Protocol) — "RDP" mentioned multiple times
- T1003.001 (LSASS Memory) — "LSASS memory dumping using Procdump" in Talos
- T1562.001 (Disable or Modify Tools) — "disabled Windows Defender" in Symantec

### 2. Entity Extraction (MIXED)

**Tools** — 29% recall. Found: psexec, wmic, fsutil, adrecon. Missed: powershell, bitsadmin, rclone, exmatter, bcdedit, ssh, scp. The pipeline depends entirely on the LLM for initial extraction — if the LLM doesn't surface a tool name, the deterministic layers can't recover it.

**Malware** — BlackCat detected, but the Talos report produced 12 "malware" objects that should be tools/techniques:
- "VSS Shadow Copy Deletion" → should be technique T1490
- "BCDEdit Recovery Disabling" → should be technique T1490
- "WMIExec" → should be tool
- "PsExec/RemCom" → should be tool
- "Apply.ps1" → should be tool (script)
- "Defender.vbscript/def.vbscript" → should be tool (script)

**Root Cause**: The LLM misclassifies entity types. The entity validator (`cti_entity_validator.py`) calls the LLM to confirm, but gemma3n frequently returns non-JSON responses (logged as `[WARN] Non-JSON response`), defaulting to "uncertain" which keeps misclassified entities.

**Actors** — BlackCat found, but "ALPHV" alias never surfaces. The NLP layer *removed* "ALPHV/BlackCat" as an actor (logged: `Actors removed: ['ALPHV/BlackCat']`) because the slash-separated format failed canonicalization.

### 3. Infrastructure (OK for what it found)

Found: C2 domain (windows.menu), C2 IPs (52.149.228.45, 20.46.245.56), VMware ESXi, ConnectWise, Tor. These are all correct.

**Bug**: IP addresses are canonicalized by stripping dots → "5214922845" and "204624556" instead of proper STIX IPv4 objects.

### 4. Relationships (CRITICAL FAILURE)

Only **2 relationships** across 141 STIX objects. For a RAG-usable knowledge graph, you need relationships like:
- BlackCat → uses → PsExec
- BlackCat → targets → VMware ESXi
- BlackCat Ransomware → uses → T1486

The relationship extractor (`cti_relationships.py`) has a code bug where `relationship_allowed()` always returns True, and the semantic relationship extraction found 0 relationships for Symantec and Talos (despite rich source text).

### 5. D3FEND Enrichment (BROKEN)

Path bug: Stage 2 looks for D3FEND assets at `plugins/mcp/plugins/mcp/utilities/D3fend_CAD/` (doubled path prefix). The D3FEND/CAD ontology files exist but are never loaded.

### 6. Reliability

- 2/5 files failed completely (Ollama crashed under load — `ServerDisconnectedError`)
- 1/5 partially failed (Talos entity validation interrupted)
- The LLM entity validator returned non-JSON in 40%+ of calls
- Pipeline has no retry logic for LLM failures
- No graceful degradation when LLM is unavailable

---

## Pipeline Stage Assessment

| Stage | Component | Status | Problem |
|-------|-----------|--------|---------|
| 1.1 | Raw → Clean | OK | Works for .txt, .html. No PDF/MHTML support |
| 1.2 | Clean → IR (LLM) | POOR | LLM extracts wrong entity types, misses key tools |
| 1.3 | NLP Layer 1 (spaCy) | MIXED | Good behavior expansion, but removes valid actors |
| 1.4 | NLP Layer 2 (WordNet) | OK | Nominalization recovery works |
| 1.5 | MITRE Matching | FAILING | Threshold too low, deprecated IDs, no disambiguation |
| 1.6 | Relationship Extraction | FAILING | Almost no relationships extracted |
| 1.7 | Entity Validation (LLM) | POOR | Non-JSON responses, uncertain = keep bad data |
| 2.1 | IR → STIX | OK | STIX construction is structurally sound |
| 2.2 | D3FEND Enrichment | BROKEN | Path bug prevents loading ontology |
| 3 | STIX → Infra Reasoning | UNTESTED | Has known code bugs |

---

## Priority Improvements (Ordered)

### P0 — Must Fix (pipeline is unusable without these)

1. **MITRE Technique Matching Overhaul**
   - Raise similarity threshold from 0.79 to 0.88+
   - Remove deprecated ATT&CK IDs (pre-v8)
   - Add disambiguation: when multiple techniques match, use the source text context to pick the best one
   - Add explicit keyword extraction for high-value techniques (T1486="encrypt", T1490="shadow copy|vssadmin", T1489="service stop|terminate process")

2. **Entity Type Classification**
   - Don't rely on LLM for entity typing. Use MITRE taxonomy lookup: if name matches a known tool in ATT&CK, classify as tool. If it matches a known malware, classify as malware
   - Scripts (.ps1, .vbs, .exe) should be classified as tools, not malware
   - Techniques described as nouns ("VSS Shadow Copy Deletion") should be mapped to attack-patterns, not malware

3. **Fix D3FEND Path Bug**
   - `cti_pipeline_stage2.py` constructs path with double prefix. Fix the path resolution.

### P1 — High Priority

4. **Relationship Extraction**
   - Fix `relationship_allowed()` to actually filter
   - Fix use-before-assignment bug in `cti_relationships.py:448-451`
   - Add template-based relationships: if entity X is in the same report as technique Y, create "X uses Y" relationship
   - Add MITRE-backed relationships from the taxonomy (20,048 pre-built relationships available)

5. **Actor Alias Resolution**
   - Handle slash-separated aliases ("ALPHV/BlackCat" → two actors with alias relationship)
   - Cross-reference MITRE Groups taxonomy for known aliases

6. **Infrastructure Canonicalization**
   - Don't strip dots from IP addresses
   - Create proper STIX IPv4-addr objects for IPs
   - Create proper STIX domain-name objects for domains

### P2 — Important

7. **LLM Reliability**
   - Add retry with exponential backoff for LLM calls
   - Add response validation: if LLM returns non-JSON, retry with stricter prompt
   - Add graceful degradation: if LLM is down, skip validation and keep all entities with "unvalidated" flag

8. **Entity Extraction Without LLM**
   - Use spaCy NER to extract entities from text directly
   - Cross-reference against MITRE taxonomy (1,778 named entities)
   - Only use LLM for entities not found in taxonomy

9. **Explicit ATT&CK ID Extraction**
   - The source texts contain explicit T-numbers (Unit42 lists T1057, T1083, T1570, T1486, T1489, T1490, T1567.002, T1090.003)
   - The pipeline doesn't extract these — it relies entirely on semantic matching
   - Add regex extraction for T\d{4}(\.\d{3})? patterns

---

## Test Reproduction

```bash
# Activate venv
source /home/caldera/Desktop/CalderaVENV/bin/activate
cd /home/caldera/Desktop/CalderaVENV/caldera

# Stage 1: raw → clean
python3 -c "from plugins.mcp.app.cti_pipeline_stage1 import step_raw_to_clean; from pathlib import Path; step_raw_to_clean(Path('plugins/mcp/data'))"

# Stage 1: clean → IR (requires Ollama running)
python3 -c "from plugins.mcp.app.cti_pipeline_stage1 import step_parse_to_ir; from pathlib import Path; step_parse_to_ir(Path('plugins/mcp/data'))"

# Stage 2: IR → STIX
python3 -c "from plugins.mcp.app.cti_pipeline_stage2 import run_phase2; from pathlib import Path; run_phase2(Path('plugins/mcp/data'))"
```

Input files: `plugins/mcp/data/raw/uploads/`
IR output: `plugins/mcp/data/outputs_ir/complete/`
STIX output: `plugins/mcp/data/outputs_stix/`
