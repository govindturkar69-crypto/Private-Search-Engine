#!/usr/bin/env bash
# run_fast_tests.sh — Run fast deterministic backend regression tests.
# Excludes e2e, performance, and slow markers.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Running fast deterministic backend tests..."
./venv/bin/pytest tests/ -v -m "not e2e and not performance and not slow"
echo "Fast deterministic tests PASSED."

