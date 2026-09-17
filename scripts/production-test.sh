#!/usr/bin/env bash
# production-test.sh — Execute production smoke test suite against running deployment.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="python"
if [ -f "./venv/bin/python" ]; then
  PYTHON_BIN="./venv/bin/python"
elif [ -f "./venv/Scripts/python.exe" ]; then
  PYTHON_BIN="./venv/Scripts/python.exe"
fi

"$PYTHON_BIN" scripts/production_smoke_test.py "$@"

