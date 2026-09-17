#!/usr/bin/env bash
# run_all_quality.sh — Run all Phase 9 quality gates in sequence.
#
# Gates (in order):
#   1. Black formatting check
#   2. Flake8 lint
#   3. Mypy type check
#   4. Backend fast regression (unit + integration + security)
#   5. Backend coverage >= 80%
#   6. Frontend TypeScript check
#   7. Frontend production build
#   8. Frontend Vitest
#
# E2E and load tests run separately (run_e2e_tests.sh / run_load_tests.sh).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PASS_GATES=()
FAIL_GATES=()

run_gate() {
    local name="$1"
    shift
    echo ""
    echo "── $name ──"
    if "$@"; then
        PASS_GATES+=("✅ $name")
    else
        FAIL_GATES+=("❌ $name")
        echo "GATE FAILED: $name"
    fi
}

run_gate "Black (format check)" \
    ./venv/bin/python -m black --check src tests

run_gate "Flake8 (lint)" \
    ./venv/bin/python -m flake8 src tests

run_gate "Mypy (type check)" \
    ./venv/bin/python -m mypy src

run_gate "Backend regression (unit + integration + security)" \
    ./venv/bin/pytest tests/ -m "not e2e and not performance and not slow" -q

run_gate "Backend coverage (>=80%)" \
    ./venv/bin/pytest tests/ \
        -m "not e2e and not performance and not slow" \
        --cov=src \
        --cov-report=term-missing \
        --cov-report=html:htmlcov \
        --cov-report=xml:coverage.xml \
        --cov-fail-under=80 \
        -q

run_gate "Frontend TypeScript (tsc --noEmit)" \
    npm run type-check --prefix frontend

run_gate "Frontend production build" \
    npm run build --prefix frontend

run_gate "Frontend Vitest" \
    npm test --prefix frontend -- --run

# --- Summary ---
echo ""
echo "============================="
echo "   Phase 9 Quality Summary   "
echo "============================="
for g in "${PASS_GATES[@]:-}"; do echo "  $g"; done
for g in "${FAIL_GATES[@]:-}"; do echo "  $g"; done
echo ""

if [ "${#FAIL_GATES[@]}" -eq 0 ]; then
    echo "All quality gates PASSED."
    exit 0
else
    echo "One or more quality gates FAILED."
    exit 1
fi

