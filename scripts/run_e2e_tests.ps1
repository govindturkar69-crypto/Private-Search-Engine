$ErrorActionPreference = "Stop"
# run_e2e_tests.ps1 — E2E Playwright test runner.
#
# Starts backend on :8001 and frontend on :3001, waits for readiness,
# runs Playwright, then tears down servers via try/finally.
#
# Requirements:
#   1. Frontend must be built first: $env:VITE_API_BASE_URL = "http://localhost:8001"
#      npm run build --prefix frontend
#   2. Backend test DB must be seeded: python scripts/seed_e2e_db.py
#   3. Playwright Chromium must be installed: python -m playwright install chromium
#   4. Set ADMIN_TOKEN=dev-admin-secret-token for E2E environment.

$BACKEND_PORT  = 8001
$FRONTEND_PORT = 3001
$BACKEND_URL   = "http://127.0.0.1:$BACKEND_PORT"
$FRONTEND_URL  = "http://127.0.0.1:$FRONTEND_PORT"
$HEALTH_URL    = "$BACKEND_URL/api/v1/health"
$E2E_DB_PATH   = "data/e2e_test.db"
$READINESS_TIMEOUT_SECS = 30
$POLL_INTERVAL_SECS     = 1

$backendProcess  = $null
$frontendProcess = $null

function Wait-ForReady {
    param([string]$Url, [string]$Name, [int]$TimeoutSecs)
    $deadline = (Get-Date).AddSeconds($TimeoutSecs)
    Write-Host "Waiting for $Name ($Url)..." -ForegroundColor DarkGray
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -lt 400) {
                Write-Host "$Name is ready." -ForegroundColor Green
                return
            }
        } catch { }
        Start-Sleep -Seconds $POLL_INTERVAL_SECS
    }
    throw "$Name did not become ready within ${TimeoutSecs}s at $Url"
}

try {
    # --- Pre-flight checks ---
    if (-not (Test-Path $E2E_DB_PATH)) {
        Write-Host "E2E database missing. Seeding now..." -ForegroundColor Yellow
        & .\venv\Scripts\python scripts\seed_e2e_db.py
        if ($LASTEXITCODE -ne 0) { throw "seed_e2e_db.py failed" }
    }

    Write-Host "Building frontend with E2E API base URL..." -ForegroundColor DarkGray
    $env:VITE_API_BASE_URL = "$BACKEND_URL/api/v1"
    npm run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }

    Write-Host ""
    Write-Host "=== Phase 9 E2E Test Runner ===" -ForegroundColor Cyan
    Write-Host "Backend  : $BACKEND_URL (DB: $E2E_DB_PATH)" -ForegroundColor DarkGray
    Write-Host "Frontend : $FRONTEND_URL" -ForegroundColor DarkGray
    Write-Host ""

    # --- Start Backend ---
    $env:ADMIN_TOKEN    = "dev-admin-secret-token"
    $env:DATABASE_URL   = $E2E_DB_PATH
    $env:DATABASE_PATH  = $E2E_DB_PATH
    $env:PORT           = "$BACKEND_PORT"
    $env:CORS_ORIGINS   = "$FRONTEND_URL,http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
    $backendArgs = @(
        "-m", "uvicorn", "src.main:create_app",
        "--host", "127.0.0.1",
        "--port", "$BACKEND_PORT",
        "--factory"
    )
    $backendProcess = Start-Process -FilePath ".\venv\Scripts\python.exe" `
        -ArgumentList $backendArgs `
        -PassThru -WindowStyle Hidden

    # --- Start Frontend Preview ---
    $frontendProcess = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run preview --prefix frontend -- --port $FRONTEND_PORT --host 127.0.0.1" `
        -PassThru -WindowStyle Hidden

    # --- Wait for readiness ---
    Wait-ForReady -Url $HEALTH_URL       -Name "Backend"  -TimeoutSecs $READINESS_TIMEOUT_SECS
    Wait-ForReady -Url $FRONTEND_URL     -Name "Frontend" -TimeoutSecs $READINESS_TIMEOUT_SECS

    # --- Run Playwright tests ---
    Write-Host ""
    Write-Host "Running Playwright E2E tests..." -ForegroundColor Cyan
    $env:E2E_BASE_URL = $FRONTEND_URL

    & .\venv\Scripts\pytest tests/test_e2e.py `
        -v `
        -m e2e

    $playwrightExit = $LASTEXITCODE

} finally {
    # --- Teardown: always stop servers ---
    Write-Host ""
    Write-Host "Stopping servers..." -ForegroundColor DarkGray
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Servers stopped." -ForegroundColor DarkGray
}

if ($playwrightExit -ne 0) {
    Write-Host "E2E tests FAILED (exit $playwrightExit)." -ForegroundColor Red
    Write-Host "Failure screenshots: test-results/e2e/" -ForegroundColor Yellow
    exit $playwrightExit
}

Write-Host "E2E tests PASSED." -ForegroundColor Green
exit 0

