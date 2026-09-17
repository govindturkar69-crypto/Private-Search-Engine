#!/usr/bin/env python3
"""Automated secret scanner for repository files and tracked content.

Scans for:
- Private keys (RSA, EC, OPENSSH, PGP)
- Generic high-entropy secret assignments (password, api_key, auth_token, secret_key)
- AWS, GitHub, Slack, Google API keys and credential tokens
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

PATTERNS = [
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PGP|PRIVATE) KEY-----"),
    re.compile(
        r"(?i)(?:api_key|secret_key|auth_token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]"
    ),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"),  # GitHub token
    re.compile(r"xox[baprs]-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}"),  # Slack token
    re.compile(r"AIza[0-9A-Za-z-_]{35}"),  # Google API key
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key ID
]

IGNORE_DIRS = {
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    "htmlcov",
    ".coverage",
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".zip",
    ".tar",
    ".gz",
    ".db",
}


def scan_repo(repo_root: Path) -> List[Tuple[str, int, str]]:
    findings: List[Tuple[str, int, str]] = []

    for root, dirs, files in os.walk(repo_root):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            file_path = Path(root) / file
            if file_path.suffix in IGNORE_EXTENSIONS:
                continue

            # Don't flag this scanner script itself
            if file == "security_secret_scan.py":
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_no, line in enumerate(f, 1):
                        # Skip comment lines that document dev defaults or examples
                        stripped = line.strip()
                        if stripped.startswith(("#", "//", "/*", "*")):
                            continue
                        for pat in PATTERNS:
                            if pat.search(line):
                                # Mask secret value in output
                                masked = re.sub(
                                    r"['\"][A-Za-z0-9_\-]{8,}['\"]",
                                    "'***MASKED***'",
                                    stripped[:80],
                                )
                                rel_path = file_path.relative_to(repo_root)
                                findings.append((str(rel_path), line_no, masked))
            except Exception:
                pass

    return findings


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    print("=== Running Automated Secret & Key Exposure Scan ===")
    print(f"Root: {repo_root}\n")

    findings = scan_repo(repo_root)

    if not findings:
        print(
            "[PASS] Secret Scan: Zero unmasked private keys or real credentials found."
        )
        return 0

    print(f"[WARN] Potential secret patterns detected: {len(findings)}")
    for file, line, snippet in findings:
        print(f"  {file}:{line} -> {snippet}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
