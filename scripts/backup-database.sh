#!/usr/bin/env bash
# backup-database.sh — Run live SQLite backup, verification, and retention.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="python"
if [ -f "./venv/bin/python" ]; then
  PYTHON_BIN="./venv/bin/python"
elif [ -f "./venv/Scripts/python.exe" ]; then
  PYTHON_BIN="./venv/Scripts/python.exe"
fi

"$PYTHON_BIN" scripts/backup_database.py "$@"

