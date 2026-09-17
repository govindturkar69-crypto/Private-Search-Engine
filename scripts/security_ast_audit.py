#!/usr/bin/env python3
"""AST-based static code security analyzer for dangerous calls and patterns.

Scans application source code (src/) for:
- eval() and exec()
- pickle.load() and pickle.loads()
- unsafe yaml.load() (without SafeLoader)
- subprocess calls with shell=True
- os.system()
- unparameterized dynamic SQL string formatting inside .execute()
"""

import ast
import sys
from pathlib import Path
from typing import Any, Dict, List


class SecurityASTVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: List[Dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # 1. Check direct function calls: eval(), exec(), os.system()
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ("eval", "exec"):
                self.findings.append(
                    {
                        "file": self.filename,
                        "line": node.lineno,
                        "severity": "CRITICAL",
                        "rule": f"dangerous-call-{func_name}",
                        "message": f"Direct invocation of {func_name}() detected.",
                    }
                )

        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            # os.system
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and attr_name == "system"
            ):
                self.findings.append(
                    {
                        "file": self.filename,
                        "line": node.lineno,
                        "severity": "HIGH",
                        "rule": "dangerous-call-os-system",
                        "message": "Direct invocation of os.system() detected.",
                    }
                )

            # pickle.load / pickle.loads
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pickle"
                and attr_name in ("load", "loads")
            ):
                self.findings.append(
                    {
                        "file": self.filename,
                        "line": node.lineno,
                        "severity": "CRITICAL",
                        "rule": f"dangerous-deserialization-pickle-{attr_name}",
                        "message": (
                            f"Insecure deserialization via pickle.{attr_name}()."
                        ),
                    }
                )

            # yaml.load without SafeLoader
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "yaml"
                and attr_name == "load"
            ):
                has_safe_loader = any(
                    kw.arg == "Loader"
                    and isinstance(kw.value, ast.Attribute)
                    and "SafeLoader" in getattr(kw.value, "attr", "")
                    for kw in node.keywords
                )
                if not has_safe_loader:
                    self.findings.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "severity": "HIGH",
                            "rule": "unsafe-yaml-load",
                            "message": (
                                "yaml.load() invoked without explicit SafeLoader."
                            ),
                        }
                    )

            # subprocess with shell=True
            if attr_name in (
                "Popen",
                "run",
                "call",
                "check_call",
                "check_output",
            ):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        if kw.value.value is True:
                            self.findings.append(
                                {
                                    "file": self.filename,
                                    "line": node.lineno,
                                    "severity": "HIGH",
                                    "rule": "subprocess-shell-true",
                                    "message": (
                                        f"subprocess.{attr_name} called "
                                        "with shell=True."
                                    ),
                                }
                            )

            # SQLite dynamic SQL string formatting in .execute()
            if attr_name == "execute" and node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.JoinedStr):  # f-string in SQL
                    self.findings.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "severity": "HIGH",
                            "rule": "dynamic-sql-fstring",
                            "message": (
                                "SQL query uses f-string formatting instead "
                                "of parameterization."
                            ),
                        }
                    )
                elif isinstance(first_arg, ast.BinOp) and isinstance(
                    first_arg.op, ast.Mod
                ):  # % formatting
                    self.findings.append(
                        {
                            "file": self.filename,
                            "line": node.lineno,
                            "severity": "HIGH",
                            "rule": "dynamic-sql-modulo",
                            "message": (
                                "SQL query uses % string formatting instead "
                                "of parameterization."
                            ),
                        }
                    )

        self.generic_visit(node)


def scan_directory(target_dir: Path) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for py_file in target_dir.rglob("*.py"):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(py_file))
            visitor = SecurityASTVisitor(str(py_file))
            visitor.visit(tree)
            findings.extend(visitor.findings)
        except Exception as e:
            print(f"Error parsing {py_file}: {e}", file=sys.stderr)
    return findings


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = repo_root / "src"

    print("=== Running AST Dangerous Call & Pattern Audit ===")
    print(f"Target: {src_dir}\n")

    findings = scan_directory(src_dir)

    if not findings:
        print(
            "[PASS] AST Audit: Zero dangerous calls (eval, exec, pickle, "
            "shell=True, dynamic SQL) found in src/."
        )
        return 0

    print(f"[WARN] Found {len(findings)} potential security pattern(s):")
    for f in findings:
        print(
            f"  [{f['severity']}] {f['file']}:{f['line']} - {f['rule']}: {f['message']}"
        )

    # Only fail on HIGH / CRITICAL
    blocking = [f for f in findings if f["severity"] in ("HIGH", "CRITICAL")]
    if blocking:
        print(f"\n[FAIL] AST Audit FAILED with {len(blocking)} blocking finding(s).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
