#!/usr/bin/env bash
# Run the mcp plugin's static PR gates in a self-contained throwaway venv.
#
# Creates a fresh virtualenv from a base python 3 interpreter (no system
# site-packages, so every dependency is installed fresh), installs tox, runs
# the gate envs defined in tox.ini (the single source of truth), and deletes
# the throwaway venv on exit.
#
# Usage:  bash tools/run-pr-gates.sh [extra tox args]
#         BASE_PY=/path/to/python3 bash tools/run-pr-gates.sh   # override base
set -uo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_PY="${BASE_PY:-$(command -v python3)}"

if [ -z "$BASE_PY" ] || [ ! -x "$BASE_PY" ]; then
    echo "run-pr-gates: base interpreter not found/executable: ${BASE_PY:-python3}" >&2
    exit 2
fi

WORK="$(mktemp -d)"
VENV="$WORK/pr-gates-venv"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

echo "run-pr-gates: building throwaway venv at $VENV from $BASE_PY (no system site-packages)"
"$BASE_PY" -m venv "$VENV"
"$VENV/bin/pip" --disable-pip-version-check -q install --upgrade pip
"$VENV/bin/pip" --disable-pip-version-check -q install 'tox>=4,<5'

cd "$PLUGIN_DIR"
# tox builds a further isolated venv per env from each env's declared deps.
"$VENV/bin/tox" -e hub-agnostic,bandit "$@"
