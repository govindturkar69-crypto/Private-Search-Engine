#!/usr/bin/env bash
# run_benchmarks.sh — Run isolated performance benchmarks (soft thresholds).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Running performance benchmarks..."
echo "  These tests report metrics but do NOT hard-fail on timing."

./venv/bin/pytest tests/ -m "performance" -v -s

echo "Performance benchmarks PASSED."

