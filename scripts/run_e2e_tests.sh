#!/usr/bin/env bash
# run_e2e_tests.sh — E2E Playwright test runner.
#
# Starts backend on :8001 and frontend on :3001, waits for readiness,
# runs Playwright tests, then tears down servers via trap.
#
# Requirements:
#   1. python scripts/seed_e2e_db.py
#   2. VITE_API_BASE_URL=http://localhost:8001 npm run build --prefix frontend
#   3. python -m playwright install chromium
#   4. ADMIN_TOKEN=dev-admin-secret-token (set below for test env)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_PORT=8001
FRONTEND_PORT=3001
BACKEND_URL="http://localhost:${BACKEND_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
HEALTH_URL="${BACKEND_URL}/api/v1/health"
E2E_DB_PATH="data/e2e_test.db"
READINESS_TIMEOUT=30
POLL_INTERVAL=1

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "Stopping servers..."
    [ -n "$BACKEND_PID"  ] && kill "$BACKEND_PID"  2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
    echo "Servers stopped."
}
trap cleanup EXIT

wait_for_ready() {
    local url="$1"
    local name="$2"
    local deadline=$(( $(date +%s) + READINESS_TIMEOUT ))
    echo "Waiting for $name ($url)..."
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if curl -sf --max-time 2 "$url" >/dev/null 2>&1; then
            echo "$name is ready."
            return 0
        fi
        sleep "$POLL_INTERVAL"
    done
    echo "ERROR: $name did not become ready within ${READINESS_TIMEOUT}s at $url" >&2
    exit 1
}

# Detect Python and Pytest binaries
PYTHON_BIN="python"
PYTEST_BIN="pytest"
if [ -f "./venv/bin/python" ]; then
    PYTHON_BIN="./venv/bin/python"
    PYTEST_BIN="./venv/bin/pytest"
elif [ -f "./venv/Scripts/python.exe" ]; then
    PYTHON_BIN="./venv/Scripts/python.exe"
    PYTEST_BIN="./venv/Scripts/pytest.exe"
fi

# --- Pre-flight checks ---
echo "Seeding E2E database..."
"$PYTHON_BIN" scripts/seed_e2e_db.py

echo "Building frontend with E2E API base URL (${BACKEND_URL}/api/v1)..."
(cd frontend && VITE_API_BASE_URL="${BACKEND_URL}/api/v1" npm run build)

echo ""
echo "=== Phase 9 E2E Test Runner ==="
echo "Backend  : $BACKEND_URL (DB: $E2E_DB_PATH)"
echo "Frontend : $FRONTEND_URL"
echo ""

# --- Start Backend ---
export ENVIRONMENT="development"
export ADMIN_TOKEN="dev-admin-secret-token"
export DATABASE_URL="$E2E_DB_PATH"
export DATABASE_PATH="$E2E_DB_PATH"
export PORT="$BACKEND_PORT"
"$PYTHON_BIN" -m uvicorn src.main:create_app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT" \
    --factory &
BACKEND_PID=$!

# --- Start Frontend Preview ---
(cd frontend && npx vite preview --port "$FRONTEND_PORT" --host 127.0.0.1) &
FRONTEND_PID=$!

# --- Wait for readiness ---
wait_for_ready "$HEALTH_URL"   "Backend"
wait_for_ready "$FRONTEND_URL" "Frontend"

# --- Run Playwright tests ---
echo ""
echo "Running Playwright E2E tests..."
export E2E_BASE_URL="$FRONTEND_URL"

"$PYTEST_BIN" tests/test_e2e.py -v -m e2e

echo ""
echo "E2E tests PASSED."

