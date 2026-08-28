#!/usr/bin/env python3
"""
Download MITRE ATT&CK 18.1 full dataset (the ONLY valid JSON file now).

Creates:
    caldera/plugins/mcp/app/cti_taxonomy/
        enterprise_attack.json
"""

import json
import requests
from pathlib import Path

MITRE_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack-18.1.json"
)

def download(url: str) -> str:
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    return r.text

def main():
    here = Path(__file__).resolve().parent
    target_dir = here.parent / "utilities/cti_taxonomy"
    target_dir.mkdir(parents=True, exist_ok=True)

    out_path = target_dir / "enterprise_attack.json"

    print(f"[+] Downloading MITRE ATT&CK → {out_path}")

    try:
        data = download(MITRE_URL)
    except Exception as e:
        print(f"[!] Download failed: {e}")
        return

    # Validate JSON
    try:
        json.loads(data)
    except Exception as e:
        print(f"[!] JSON validation failed: {e}")
        return

    out_path.write_text(data, encoding="utf-8")
    print(f"[+] Saved enterprise_attack.json ({out_path.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
