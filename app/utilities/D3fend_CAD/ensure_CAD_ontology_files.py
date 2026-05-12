#!/usr/bin/env python3
"""
Standalone D3FEND ontology fetch/update utility.

Automatically:
    - Clones or updates the d3fend GitHub repository
    - Locates ontology .ttl files regardless of folder layout
    - Locates mappings directory
    - Locates CAD schema
"""

import argparse
import subprocess
from pathlib import Path

D3FEND_GIT_URL = "https://github.com/d3fend/d3fend-ontology.git"


def find_file(root: Path, patterns):
    """Return first file matching any pattern below a directory."""
    if isinstance(patterns, str):
        patterns = [patterns]

    for pattern in patterns:
        matches = list(root.rglob(pattern))
        if matches:
            return matches[0]
    return None


def ensure_ontology_files(ontology_root: Path):
    """
    Ensures the d3fend ontology is cloned and returns paths to:
      - ALL TTL ontology modules under src/ontology/
      - mappings directory
      - CAD schema
    """

    repo_dir = ontology_root / "d3fend-ontology"

    if repo_dir.exists():
        print("[D3FEND] Updating existing repository...")
        subprocess.run(["git", "-C", str(repo_dir), "pull"], check=False)
    else:
        print("[D3FEND] Cloning ontology repository...")
        subprocess.run(["git", "clone", D3FEND_GIT_URL, str(repo_dir)], check=True)

    # Correct modern repo structure
    src_ontology_dir = repo_dir / "src" / "ontology"
    mappings_dir     = src_ontology_dir / "mappings"
    cad_schema       = repo_dir / "cad" / "schema" / "cad.schema.json"

    # Collect ALL TTL ontology files
    ttl_files = list(src_ontology_dir.rglob("*.ttl"))

    if not ttl_files:
        raise FileNotFoundError(
            f"No TTL ontology files found under {src_ontology_dir}"
        )

    if not cad_schema.exists():
        raise FileNotFoundError(f"Missing CAD schema: {cad_schema}")

    if not mappings_dir.exists():
        raise FileNotFoundError(f"Missing mappings directory: {mappings_dir}")

    print(f"[D3FEND] Loaded {len(ttl_files)} ontology TTL modules.")

    return {
        "ontology_modules": ttl_files,
        "mappings": mappings_dir,
        "cad_schema": cad_schema,
    }

def main():
    parser = argparse.ArgumentParser(description="Fetch and validate the D3FEND ontology + CAD schema")
    parser.add_argument(
        "--ontology-root",
        type=Path,
        default=Path("./ontology"),
        help="Directory where the D3FEND ontology repo will be stored."
    )

    args = parser.parse_args()
    args.ontology_root.mkdir(parents=True, exist_ok=True)

    result = ensure_ontology_files(args.ontology_root)

    print("\n[D3FEND] Ontology and CAD schema ready.")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
