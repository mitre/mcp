# CTI pipeline measuring sticks

Reference STIX bundles that represent **what the MCP CTI pipeline should produce** for well-known threats. These exist to score actual pipeline output — diff them against the bundle the pipeline emits, and the delta is your work list.

**Hard rule**: every value in these reference bundles must be derivable from an ontology or dictionary (MITRE ATT&CK, MITRE D3fend, STIX 2.1 open vocab, NIST controls). If you'd need a hardcoded lookup table to produce a field, that field doesn't belong in the measuring stick — the pipeline can't be expected to invent it either.

## Files

- [`blackcat-expected.stix.json`](blackcat-expected.stix.json) — BlackCat (ALPHV) ransomware. **Auto-derived** from the ATT&CK Evaluations `attackevals-ael/ManagedServices/alphv_blackcat` plan via `plugins/mcp/app/utilities/cti_ae_library_loader.py`. Regenerate with:

  ```bash
  python -m plugins.mcp.app.utilities.cti_ae_library_loader \
    --adversary blackcat \
    --emit-stix plugins/mcp/data/measuring-sticks/blackcat-expected.stix.json
  ```

- [`blackcat-expected.handcrafted.stix.json`](blackcat-expected.handcrafted.stix.json) — the original hand-crafted measuring stick, retained so the gap between "what we hand-said" and "what the AE plan actually says" can be diffed.

## How to use

```python
import json, deepdiff
expected = json.load(open("blackcat-expected.stix.json"))
actual   = json.load(open("plugins/mcp/data/outputs_stix/<run>.stix.json"))
diff = deepdiff.DeepDiff(expected, actual, ignore_order=True)
# Inspect diff — every key in expected that's missing/different in actual is a pipeline gap.
```

## What "complete" means here

Per STIX 2.1 spec ([Infrastructure SDO](https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html#_jo3k1o6lr9)):

Required:
- `type: "infrastructure"`, `spec_version: "2.1"`, `id`, `created`, `modified`, `name`

Recommended (the measuring stick fills these):
- `infrastructure_types` — from STIX open vocab `infrastructure-type-ov`: `amplification | anonymization | botnet | command-and-control | control-system | exfiltration | firewall | hosting-malware | hosting-target-lists | phishing | reconnaissance | routers-switches | staging | unknown | workstation`
- `description`, `aliases`, `kill_chain_phases`, `first_seen`, `last_seen`

Topology inference was removed: the pipeline no longer emits a per-host
topology object, and the expected bundles intentionally have none. Hosts,
accounts and domains named in a report describe the previous victim, so they
are not turned into CALDERA facts either. CALDERA discovers facts about the
operator's own estate at runtime.
