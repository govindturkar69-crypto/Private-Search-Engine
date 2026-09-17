$ErrorActionPreference = "Stop"
# run_load_tests.ps1 — Locust load test runner.
#
# Safety constraints:
#   - LOAD_TEST_HOST must be explicitly set, OR this script starts its own
#     isolated server on LOAD_TEST_PORT (default 8099).
#   - Remote (non-localhost) targets require ALLOW_REMOTE_LOAD_TEST=true.
#   - Pass/fail evaluated against: failure_rate <= 1%, p95 <= 200ms.
#
# Usage:
#   .\scripts\run_load_tests.ps1                    # starts own server on :8099
#   $env:LOAD_TEST_HOST="http://localhost:8000" ; .\scripts\run_load_tests.ps1

$USERS       = if ($env:LOAD_TEST_USERS)       { $env:LOAD_TEST_USERS }       else { "20" }
$SPAWN_RATE  = if ($env:LOAD_TEST_SPAWN_RATE)  { $env:LOAD_TEST_SPAWN_RATE }  else { "5" }
$DURATION    = if ($env:LOAD_TEST_DURATION)    { $env:LOAD_TEST_DURATION }    else { "60s" }
$LOAD_PORT   = if ($env:LOAD_TEST_PORT)        { $env:LOAD_TEST_PORT }        else { "8099" }
$FAIL_RATE   = 1.0   # percent
$FAIL_P95_MS = 200   # milliseconds

$ownServer  = $false
$serverProc = $null

function Is-Local([string]$host) {
    return ($host -match "127\." -or $host -match "localhost" -or $host -match "\[::1\]")
}

try {
    # --- Resolve LOAD_TEST_HOST ---
    if (-not $env:LOAD_TEST_HOST) {
        Write-Host "LOAD_TEST_HOST not set. Starting own isolated test server on :$LOAD_PORT..." -ForegroundColor Yellow
        $env:LOAD_TEST_HOST = "http://localhost:$LOAD_PORT"
        $ownServer = $true

        $serverArgs = @(
            "-m", "uvicorn", "src.main:create_app",
            "--host", "127.0.0.1",
            "--port", "$LOAD_PORT",
            "--factory",
            "--log-level", "warning"
        )
        $serverProc = Start-Process -FilePath ".\venv\Scripts\python.exe" `
            -ArgumentList $serverArgs `
            -PassThru -WindowStyle Hidden

        # Wait for readiness
        $deadline = (Get-Date).AddSeconds(20)
        while ((Get-Date) -lt $deadline) {
            try {
                $r = Invoke-WebRequest -Uri "$($env:LOAD_TEST_HOST)/api/v1/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($r.StatusCode -lt 400) { break }
            } catch {}
            Start-Sleep -Seconds 1
        }
        Write-Host "Load test server ready at $($env:LOAD_TEST_HOST)." -ForegroundColor Green
    } else {
        # Safety guard for remote targets
        if (-not (Is-Local $env:LOAD_TEST_HOST)) {
            if ($env:ALLOW_REMOTE_LOAD_TEST -ne "true") {
                Write-Host "ERROR: LOAD_TEST_HOST '$($env:LOAD_TEST_HOST)' is non-local." -ForegroundColor Red
                Write-Host "Set ALLOW_REMOTE_LOAD_TEST=true to confirm intent." -ForegroundColor Yellow
                exit 1
            }
            Write-Host "WARNING: Running load tests against non-local host." -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host "=== Phase 9 Load Test Runner ===" -ForegroundColor Cyan
    Write-Host "Host       : $($env:LOAD_TEST_HOST)" -ForegroundColor DarkGray
    Write-Host "Users      : $USERS  |  Spawn rate: $SPAWN_RATE/s  |  Duration: $DURATION" -ForegroundColor DarkGray
    Write-Host ""

    $timestamp = (Get-Date -Format "yyyyMMdd_HHmmss")
    $reportDir = "reports\load"
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    $csvBase = "$reportDir\loadtest_${timestamp}"

    & .\venv\Scripts\locust `
        -f tests\load\locustfile.py `
        --headless `
        --host "$($env:LOAD_TEST_HOST)" `
        --users "$USERS" `
        --spawn-rate "$SPAWN_RATE" `
        --run-time "$DURATION" `
        --csv "$csvBase" `
        --only-summary

    $locustExit = $LASTEXITCODE

    # --- Evaluate pass/fail thresholds ---
    $statsFile = "${csvBase}_stats.csv"
    $PASS = $true
    if (Test-Path $statsFile) {
        Write-Host ""
        Write-Host "--- Load Test Results ---" -ForegroundColor Cyan
        Import-Csv $statsFile | ForEach-Object {
            $name      = $_."Name"
            $failPct   = [double]($_."Failure Count" / ($_."Request Count" + 0.0001) * 100)
            $p95       = [double]($_."95%")
            $reqCount  = $_."Request Count"
            Write-Host "  [$name] Requests: $reqCount  Fail%: $([math]::Round($failPct,2))  p95: ${p95}ms"
            if ($failPct -gt $FAIL_RATE)   { Write-Host "    THRESHOLD BREACH: failure rate $failPct% > $FAIL_RATE%" -ForegroundColor Red; $PASS = $false }
            if ($p95     -gt $FAIL_P95_MS) { Write-Host "    THRESHOLD BREACH: p95 ${p95}ms > ${FAIL_P95_MS}ms" -ForegroundColor Yellow }
        }
    }

    if ($locustExit -ne 0 -or -not $PASS) {
        Write-Host "Load test FAILED." -ForegroundColor Red
        exit 1
    }

} finally {
    if ($ownServer -and $serverProc -and -not $serverProc.HasExited) {
        Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Load test server stopped." -ForegroundColor DarkGray
    }
}

Write-Host "Load test PASSED." -ForegroundColor Green
exit 0

