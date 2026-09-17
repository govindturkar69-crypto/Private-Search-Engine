$ErrorActionPreference = "Stop"
# production-test.ps1 — Execute production smoke test suite against running deployment.

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $REPO_ROOT

$PYTHON = "python"
if (Test-Path ".\venv\Scripts\python.exe") {
    $PYTHON = ".\venv\Scripts\python.exe"
}

& $PYTHON scripts/production_smoke_test.py @args
exit $LASTEXITCODE

