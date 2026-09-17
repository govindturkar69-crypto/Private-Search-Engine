$ErrorActionPreference = "Stop"
# run_all_quality.ps1 — Run all Phase 9 quality gates in sequence.
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
# NOTE: E2E and load tests are NOT included here — run them separately via
#       run_e2e_tests.ps1 and run_load_tests.ps1.

$gates = @()

function Run-Gate([string]$Name, [scriptblock]$Cmd) {
    Write-Host ""
    Write-Host "── $Name ──" -ForegroundColor Cyan
    & $Cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "GATE FAILED: $Name" -ForegroundColor Red
        $script:gates += "❌ $Name"
        return $false
    }
    $script:gates += "✅ $Name"
    return $true
}

$allPassed = $true

# Gate 1: Black
$ok = Run-Gate "Black (format check)" {
    & .\venv\Scripts\python -m black --check src tests
}
if (-not $ok) { $allPassed = $false }

# Gate 2: Flake8
$ok = Run-Gate "Flake8 (lint)" {
    & .\venv\Scripts\python -m flake8 src tests
}
if (-not $ok) { $allPassed = $false }

# Gate 3: Mypy
$ok = Run-Gate "Mypy (type check)" {
    & .\venv\Scripts\python -m mypy src
}
if (-not $ok) { $allPassed = $false }

# Gate 4: Backend regression
$ok = Run-Gate "Backend regression (unit + integration + security)" {
    & .\venv\Scripts\pytest tests/ -m "not e2e and not performance and not slow" -q
}
if (-not $ok) { $allPassed = $false }

# Gate 5: Coverage
$ok = Run-Gate "Backend coverage (>=80%)" {
    & .\venv\Scripts\pytest tests/ `
        -m "not e2e and not performance and not slow" `
        --cov=src `
        --cov-report=term-missing `
        --cov-report=html:htmlcov `
        --cov-report=xml:coverage.xml `
        --cov-fail-under=80 `
        -q
}
if (-not $ok) { $allPassed = $false }

# Gate 6: TypeScript
$ok = Run-Gate "Frontend TypeScript (tsc --noEmit)" {
    npm run type-check --prefix frontend
}
if (-not $ok) { $allPassed = $false }

# Gate 7: Frontend build
$ok = Run-Gate "Frontend production build" {
    npm run build --prefix frontend
}
if (-not $ok) { $allPassed = $false }

# Gate 8: Vitest
$ok = Run-Gate "Frontend Vitest" {
    npm test --prefix frontend -- --run
}
if (-not $ok) { $allPassed = $false }

# --- Summary ---
Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "   Phase 9 Quality Summary   " -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
foreach ($gate in $gates) {
    Write-Host "  $gate"
}
Write-Host ""

if ($allPassed) {
    Write-Host "All quality gates PASSED." -ForegroundColor Green
    exit 0
} else {
    Write-Host "One or more quality gates FAILED." -ForegroundColor Red
    exit 1
}

