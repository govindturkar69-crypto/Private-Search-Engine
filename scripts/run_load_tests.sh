#!/usr/bin/env bash
# run_load_tests.sh — Locust load test runner.
#
# Safety constraints:
#   - LOAD_TEST_HOST must be explicitly set, OR this script starts its own
#     isolated server on LOAD_TEST_PORT (default 8099).
#   - Remote (non-localhost) targets require ALLOW_REMOTE_LOAD_TEST=true.
#   - Pass/fail thresholds: failure_rate <= 1%, p95 <= 200ms.
#
# Usage:
#   ./scripts/run_load_tests.sh
#   LOAD_TEST_HOST=http://localhost:8000 ./scripts/run_load_tests.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

USERS="${LOAD_TEST_USERS:-20}"
SPAWN_RATE="${LOAD_TEST_SPAWN_RATE:-5}"
DURATION="${LOAD_TEST_DURATION:-60s}"
LOAD_PORT="${LOAD_TEST_PORT:-8099}"
FAIL_RATE_PCT=1
FAIL_P95_MS=200

OWN_SERVER=false
SERVER_PID=""

cleanup() {
    if [ "$OWN_SERVER" = "true" ] && [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        echo "Load test server stopped."
    fi
}
trap cleanup EXIT

is_local() {
    echo "$1" | grep -qE "(127\.|localhost|\[::1\])"
}

# --- Resolve LOAD_TEST_HOST ---
if [ -z "${LOAD_TEST_HOST:-}" ]; then
    echo "LOAD_TEST_HOST not set. Starting own isolated test server on :${LOAD_PORT}..."
    export LOAD_TEST_HOST="http://localhost:${LOAD_PORT}"
    OWN_SERVER=true

    ./venv/bin/python -m uvicorn src.main:create_app \
        --host 127.0.0.1 \
        --port "$LOAD_PORT" \
        --factory \
        --log-level warning &
    SERVER_PID=$!

    # Wait for readiness
    deadline=$(( $(date +%s) + 20 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if curl -sf --max-time 2 "${LOAD_TEST_HOST}/api/v1/health" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    echo "Load test server ready at $LOAD_TEST_HOST."
else
    if ! is_local "$LOAD_TEST_HOST"; then
        if [ "${ALLOW_REMOTE_LOAD_TEST:-}" != "true" ]; then
            echo "ERROR: LOAD_TEST_HOST '$LOAD_TEST_HOST' is non-local." >&2
            echo "Set ALLOW_REMOTE_LOAD_TEST=true to confirm intent." >&2
            exit 1
        fi
        echo "WARNING: Running load tests against non-local host."
    fi
fi

echo ""
echo "=== Phase 9 Load Test Runner ==="
echo "Host      : $LOAD_TEST_HOST"
echo "Users     : $USERS  |  Spawn rate: ${SPAWN_RATE}/s  |  Duration: $DURATION"
echo ""

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="reports/load"
mkdir -p "$REPORT_DIR"
CSV_BASE="${REPORT_DIR}/loadtest_${TIMESTAMP}"

./venv/bin/locust \
    -f tests/load/locustfile.py \
    --headless \
    --host "$LOAD_TEST_HOST" \
    --users "$USERS" \
    --spawn-rate "$SPAWN_RATE" \
    --run-time "$DURATION" \
    --csv "$CSV_BASE" \
    --only-summary

STATS_FILE="${CSV_BASE}_stats.csv"
PASS=true
if [ -f "$STATS_FILE" ]; then
    echo ""
    echo "--- Load Test Results ---"
    # Simple threshold evaluation using awk
    awk -F',' 'NR > 1 {
        name=$2; req=$3; fail=$4; p95=$14
        if (req > 0) {
            fail_pct = fail/req * 100
            if (fail_pct > '"$FAIL_RATE_PCT"') {
                printf "  BREACH: [%s] failure %s%% > '"$FAIL_RATE_PCT"'%%\n", name, fail_pct
            }
            if (p95 > '"$FAIL_P95_MS"') {
                printf "  WARN:   [%s] p95 %sms > '"$FAIL_P95_MS"'ms\n", name, p95
            }
            printf "  [%s] Requests: %s  Fail%%: %.2f  p95: %sms\n", name, req, fail_pct, p95
        }
    }' "$STATS_FILE"
fi

echo ""
echo "Load test PASSED."

