$ErrorActionPreference = "Stop"
# run_coverage.ps1 — Run backend coverage and enforce >=80% threshold.

$threshold = 80

Write-Host "Running backend coverage (threshold: $threshold%)..." -ForegroundColor Cyan

& .\venv\Scripts\pytest tests/ `
    -m "not e2e and not performance and not slow" `
    --cov=src `
    --cov-report=term-missing `
    --cov-report=html:htmlcov `
    --cov-report=xml:coverage.xml `
    --cov-fail-under=$threshold `
    -q

if ($LASTEXITCODE -ne 0) {
    Write-Host "Coverage gate FAILED (threshold: $threshold%)." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Coverage gate PASSED (>= $threshold%)." -ForegroundColor Green
Write-Host "HTML report: htmlcov/index.html" -ForegroundColor DarkGray
exit 0

