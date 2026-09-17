$ErrorActionPreference = "Stop"
# run_benchmarks.ps1 — Run isolated performance benchmarks (soft thresholds).
# NOTE: Excluded from normal regression; run explicitly.

Write-Host "Running performance benchmarks..." -ForegroundColor Cyan
Write-Host "  These tests report metrics but do NOT hard-fail on timing." -ForegroundColor DarkGray

& .\venv\Scripts\pytest tests/ -m "performance" -v -s

if ($LASTEXITCODE -ne 0) {
    Write-Host "Performance benchmarks reported unexpected failures." -ForegroundColor Yellow
    Write-Host "Review output above — timing assertions may need calibration." -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host "Performance benchmarks PASSED." -ForegroundColor Green
exit 0

