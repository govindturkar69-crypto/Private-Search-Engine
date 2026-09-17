#!/usr/bin/env bash
# run_security_scan.sh — Multi-scanner security scan runner.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Running production security scan suite..."

./venv/bin/python scripts/security_scan.py
SCAN_EXIT=$?

if [ "$SCAN_EXIT" -eq 0 ]; then
    echo -e "\nSecurity scan PASSED (no blocking vulnerabilities)."
    exit 0
elif [ "$SCAN_EXIT" -eq 1 ]; then
    echo -e "\nSecurity scan reported BLOCKING FINDINGS."
    exit 1
else
    echo -e "\nSecurity scan encountered TOOL/CONFIGURATION ERROR."
    exit "$SCAN_EXIT"
fi

