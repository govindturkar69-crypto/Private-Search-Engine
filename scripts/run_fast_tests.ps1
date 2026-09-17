$ErrorActionPreference = "Stop"
# run_fast_tests.ps1 — Run fast deterministic backend regression tests.
# Excludes e2e, performance, and slow markers.

Write-Host "Running fast deterministic backend tests..." -ForegroundColor Cyan
& .\venv\Scripts\pytest tests/ -v -m "not e2e and not performance and not slow"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Fast backend regression tests FAILED." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "Fast deterministic tests PASSED." -ForegroundColor Green
exit 0
