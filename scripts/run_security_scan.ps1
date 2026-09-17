$ErrorActionPreference = "Stop"
# run_security_scan.ps1 — Multi-scanner security scan runner.

Write-Host "Running production security scan suite..." -ForegroundColor Cyan

& .\venv\Scripts\python scripts\security_scan.py

$scanExit = $LASTEXITCODE

if ($scanExit -eq 0) {
    Write-Host "`nSecurity scan PASSED (no blocking vulnerabilities)." -ForegroundColor Green
    exit 0
} elseif ($scanExit -eq 1) {
    Write-Host "`nSecurity scan reported BLOCKING FINDINGS." -ForegroundColor Red
    exit 1
} else {
    Write-Host "`nSecurity scan encountered TOOL/CONFIGURATION ERROR." -ForegroundColor Red
    exit $scanExit
}

