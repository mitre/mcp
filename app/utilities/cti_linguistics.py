"""File hash observables for Stage 1.

Everything else this module carried, behaviour normalisation, fuzzy entity
canonicalisation, entity typing and dynamic linguistic technique extraction,
had no caller. The extraction of malware, tools and infrastructure it fed was
removed once convert_ir_to_stix was confirmed never to read them.
"""

import re

# ===========================================================
# Attempt to capture hash-like strings
# ===========================================================
HASH_PATTERNS = {
    "MD5": re.compile(r"\b[a-fA-F0-9]{32}\b"),
    "SHA1": re.compile(r"\b[a-fA-F0-9]{40}\b"),
    "SHA256": re.compile(r"\b[a-fA-F0-9]{64}\b"),
    "SHA512": re.compile(r"\b[a-fA-F0-9]{128}\b"),
}


def extract_hashes(text: str) -> list[dict]:
    """
    Extract cryptographic hashes from CTI text.

    Returns:
        [
            {
                "hash_type": "SHA256",
                "hash": "<value>",
                "evidence": "<sentence>"
            }
        ]
    """
    results = []
    seen = set()

    for line in text.splitlines():
        for htype, pattern in HASH_PATTERNS.items():
            for match in pattern.findall(line):
                key = (htype, match)
                if key in seen:
                    continue
                seen.add(key)

                results.append({
                    "hash_type": htype,
                    "hash": match.lower(),
                    "evidence": line.strip(),
                })

    return results














