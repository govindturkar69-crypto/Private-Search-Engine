#!/usr/bin/env bash
# run_coverage.sh — Run backend coverage and enforce >=80% threshold.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

THRESHOLD=80

echo "Running backend coverage (threshold: ${THRESHOLD}%)..."

./venv/bin/pytest tests/ \
    -m "not e2e and not performance and not slow" \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    --cov-report=xml:coverage.xml \
    --cov-fail-under="$THRESHOLD" \
    -q

echo "Coverage gate PASSED (>= ${THRESHOLD}%)."
echo "HTML report: htmlcov/index.html"

