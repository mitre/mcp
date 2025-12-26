"""
cti_raw_parser.py

A lightweight CTI text parser used when no Phase-1 IR exists.
This creates a very rough "IR-lite" structure to allow:

- Scenario generation from raw text
- Baseline comparison with Phase1+Phase2 scenarios

This does NOT attempt full entity/behavior extraction.
Instead, it detects common CTI markers and extracts:
    - Threat actors
    - Malware names
    - Tools
    - Infrastructure references
    - Behaviors (verbs + action phrases)

This is used ONLY when scenario-only is requested and no complete_*.json exists.
"""

import re
from typing import Dict, List


def extract_lines(text: str) -> List[str]:
    return [l.strip() for l in text.splitlines() if l.strip()]


# ----------------------------------------------------------------------
# Basic extractors (very lightweight)
# ----------------------------------------------------------------------

ACTOR_PATTERNS = [
    r"\b([A-Z][a-zA-Z0-9]{3,} Group)\b",
    r"\b([A-Z][a-zA-Z0-9]{3,} Team)\b",
    r"\b(UNC[0-9]{3,})\b",
    r"\b(Storm-[0-9]{2,})\b",
    r"\b(Cluster [A-Z0-9]{1,4})\b",
]

MALWARE_PATTERNS = [
    r"\b([A-Z][a-zA-Z0-9]{3,}Bot)\b",
    r"\b([A-Z][a-zA-Z0-9]{3,}Loader)\b",
    r"\b([A-Z][a-zA-Z0-9]{3,}Stealer)\b",
    r"\b([A-Z][a-zA-Z0-9]{3,}RAT)\b",
    r"\b([A-Z][a-zA-Z0-9]{3,}Backdoor)\b",
]

TOOL_PATTERNS = [
    r"\b(PowerShell)\b",
    r"\b(WMI)\b",
    r"\b(RDP)\b",
    r"\b(Mimikatz)\b",
    r"\b(Cobalt Strike)\b",
]

INFRA_PATTERNS = [
    r"\b([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\b",
    r"\b([a-zA-Z0-9\-]+\.[a-z]{2,8})\b",
]


BEHAVIOR_VERBS = [
    "executed", "deployed", "exfiltrated", "encrypted",
    "scanned", "lateral", "moved", "persisted", "downloaded",
    "uploaded", "communicated", "connected", "delivered",
    "installed", "dropped"
]


def extract_pattern_list(text: str, patterns: List[str]) -> List[str]:
    out = set()
    for pat in patterns:
        for m in re.findall(pat, text, re.IGNORECASE):
            if isinstance(m, tuple):
                out.add(m[0])
            else:
                out.add(m)
    return sorted(out)


def extract_behaviors(text: str) -> List[Dict[str, str]]:
    behaviors = []
    lines = extract_lines(text)

    for line in lines:
        for verb in BEHAVIOR_VERBS:
            if verb in line.lower():
                behaviors.append({"description": line})

    return behaviors


# ----------------------------------------------------------------------
# Public function
# ----------------------------------------------------------------------

def parse_raw_cti(text: str) -> Dict:
    """
    Produce a minimal IR-like dictionary from raw text.
    """

    return {
        "threat_actors": [{"name": a} for a in extract_pattern_list(text, ACTOR_PATTERNS)],
        "malware": [{"name": m} for m in extract_pattern_list(text, MALWARE_PATTERNS)],
        "tools": [{"name": t} for t in extract_pattern_list(text, TOOL_PATTERNS)],
        "infrastructure": [{"name": i} for i in extract_pattern_list(text, INFRA_PATTERNS)],
        "behaviors": extract_behaviors(text),
        "attack_patterns": [],  # raw can't infer TTPs reliably
        "relationships": []     # raw can't infer relationships
    }
