#!/usr/bin/env python3
"""
Unit tests for cti_relation_extractor.py

Tests relationship extraction across diverse CTI writing styles,
threat actors, and sentence structures. Not tuned to any specific
adversary — tests must pass for ANY CTI data.

Run: python3 -m pytest tests/test_relation_extractor.py -v
  or: python3 tests/test_relation_extractor.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parents[1]))

from plugins.mcp.app.utilities.cti_relation_extractor import (
    extract_triples,
    filter_grounded_relationships,
    dedup_triples,
)

# ============================================================
# TEST SENTENCES — diverse actors, styles, structures
# ============================================================

TEST_CASES = [
    # ── ACTIVE VOICE, SIMPLE ──
    {
        "name": "active_simple_apt29",
        "text": "APT29 uses Cobalt Strike for command and control.",
        "entities": {"apt29", "cobalt strike"},
        "expect_min": 1,
        "expect_contains": [("apt29", "use", "cobalt strike")],
    },
    {
        "name": "active_simple_lazarus",
        "text": "Lazarus Group deployed ELECTRICFISH to establish encrypted tunnels.",
        "entities": {"lazarus group", "electricfish"},
        "expect_min": 1,
        "expect_contains": [("lazarus group", "deploy", "electricfish")],
    },

    # ── COMPOUND SUBJECT ──
    {
        "name": "compound_subject_blackcat",
        "text": "BlackCat operators leverage Mimikatz to recover stored passwords.",
        "entities": {"blackcat", "mimikatz"},
        "expect_min": 1,
        "expect_source": "blackcat",
    },
    {
        "name": "compound_subject_apt28",
        "text": "APT28 actors deployed X-Agent across compromised hosts.",
        "entities": {"apt28", "x-agent"},
        "expect_min": 1,
        "expect_source": "apt28",
    },
    {
        "name": "compound_subject_fin7",
        "text": "FIN7 members utilized Carbanak malware to access banking systems.",
        "entities": {"fin7", "carbanak"},
        "expect_min": 1,
        "expect_source": "fin7",
    },

    # ── CONJUNCTION SPLITTING ──
    {
        "name": "conjunction_three_tools",
        "text": "The group deployed AnyDesk, TeamViewer and Cobalt Strike for remote access.",
        "entities": {"anydesk", "teamviewer", "cobalt strike"},
        "expect_min": 2,  # Should get at least 2 of the 3
    },
    {
        "name": "conjunction_two_malware",
        "text": "Sandworm deployed NotPetya and Industroyer against Ukrainian infrastructure.",
        "entities": {"sandworm", "notpetya", "industroyer"},
        "expect_min": 2,
        "expect_source": "sandworm",
    },
    {
        "name": "conjunction_exfil_tools",
        "text": "The attackers used rclone and MEGAsync to exfiltrate sensitive data.",
        "entities": {"rclone", "megasync"},
        "expect_min": 1,
    },

    # ── PASSIVE VOICE ──
    {
        "name": "passive_deployed_by",
        "text": "Mimikatz was deployed by the BlackCat operators to dump LSASS.",
        "entities": {"blackcat", "mimikatz", "lsass"},
        "expect_min": 1,
        "expect_source": "blackcat",
        "expect_target": "mimikatz",
    },
    {
        "name": "passive_used_by",
        "text": "PsExec was used by the threat actor to execute ransomware on remote hosts.",
        "entities": {"psexec"},
        "expect_min": 1,
        "expect_target": "psexec",
    },
    {
        "name": "passive_exploited_by",
        "text": "ConnectWise was exploited by ALPHV to gain initial access.",
        "entities": {"alphv", "connectwise"},
        "expect_min": 1,
        "expect_source": "alphv",
    },

    # ── ONTOLOGY GROUNDING ──
    {
        "name": "no_entities_should_produce_nothing",
        "text": "The researchers analyzed the sample in a sandbox environment.",
        "entities": set(),
        "expect_min": 0,
        "expect_max": 0,
    },
    {
        "name": "reporter_verb_should_be_skipped",
        "text": "Symantec researchers identified Noberus as a new ransomware variant.",
        "entities": {"noberus"},
        "expect_min": 0,  # "identified" is a reporter verb
    },

    # ── DIVERSE THREAT ACTORS ──
    {
        "name": "turla_snake",
        "text": "Turla leveraged the Snake implant for persistent access to government networks.",
        "entities": {"turla", "snake"},
        "expect_min": 1,
        "expect_source": "turla",
    },
    {
        "name": "muddywater_powershell",
        "text": "MuddyWater executed PowerShell scripts to download additional payloads.",
        "entities": {"muddywater", "powershell"},
        "expect_min": 1,
        "expect_source": "muddywater",
    },
    {
        "name": "conti_ransomware",
        "text": "Conti operators used BazarLoader to deliver the ransomware payload.",
        "entities": {"conti", "bazarloader"},
        "expect_min": 1,
        "expect_source": "conti",
    },

    # ── COMPLEX SENTENCES ──
    {
        "name": "multi_clause",
        "text": "After gaining initial access, Volt Typhoon used living-off-the-land binaries to move laterally.",
        "entities": {"volt typhoon"},
        "expect_min": 1,
        "expect_source": "volt typhoon",
    },
    {
        "name": "infrastructure_target",
        "text": "The malware connects to the C2 server at evil.example.com on port 443.",
        "entities": {"evil.example.com"},
        "expect_min": 1,
        "expect_target": "evil.example.com",
    },
]


# ============================================================
# TEST RUNNER
# ============================================================

def run_tests():
    passed = 0
    failed = 0
    total = len(TEST_CASES)

    print(f"Running {total} relationship extraction tests\n")
    print(f"{'Test':<40} {'Result':>8} {'Found':>6} {'Expected':>9} {'Details'}")
    print(f"{'-'*40} {'-'*8} {'-'*6} {'-'*9} {'-'*30}")

    for tc in TEST_CASES:
        name = tc["name"]
        text = tc["text"]
        entities = tc["entities"]
        expect_min = tc.get("expect_min", 1)
        expect_max = tc.get("expect_max", 999)
        expect_source = tc.get("expect_source")
        expect_target = tc.get("expect_target")
        expect_contains = tc.get("expect_contains", [])

        # Run extraction
        triples = extract_triples(text, entities)
        filtered = filter_grounded_relationships(triples)
        deduped = dedup_triples(filtered)

        # Evaluate
        ok = True
        details = []

        if len(deduped) < expect_min:
            ok = False
            details.append(f"too few ({len(deduped)}<{expect_min})")

        if len(deduped) > expect_max:
            ok = False
            details.append(f"too many ({len(deduped)}>{expect_max})")

        if expect_source:
            sources = {r["source"].lower() for r in deduped}
            if not any(expect_source in s for s in sources):
                ok = False
                details.append(f"missing source '{expect_source}'")

        if expect_target:
            targets = {r["target"].lower() for r in deduped}
            if not any(expect_target in t for t in targets):
                ok = False
                details.append(f"missing target '{expect_target}'")

        for exp_src, exp_verb, exp_tgt in expect_contains:
            found = False
            for r in deduped:
                if (exp_src in r["source"].lower() and
                    exp_verb in r["relationship"] and
                    exp_tgt in r["target"].lower()):
                    found = True
                    break
            if not found:
                ok = False
                details.append(f"missing ({exp_src}→{exp_verb}→{exp_tgt})")

        if ok:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        detail_str = "; ".join(details) if details else ""
        if deduped and not details:
            # Show what we found
            r = deduped[0]
            detail_str = f"{r['source']}→{r['relationship']}→{r['target']}"

        print(f"{name:<40} {status:>8} {len(deduped):>6} {f'>={expect_min}':>9} {detail_str}")

    print(f"\n{'='*70}")
    print(f"RESULTS: {passed}/{total} passed ({100*passed/total:.0f}%), {failed} failed")
    print(f"{'='*70}")

    return passed, failed


if __name__ == "__main__":
    passed, failed = run_tests()
    sys.exit(1 if failed > 0 else 0)
