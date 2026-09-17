$ErrorActionPreference = "Stop"
# backup-database.ps1 — Run live SQLite backup, verification, and retention.

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $REPO_ROOT

$PYTHON = "python"
if (Test-Path ".\venv\Scripts\python.exe") {
    $PYTHON = ".\venv\Scripts\python.exe"
}

& $PYTHON scripts/backup_database.py @args
exit $LASTEXITCODE

