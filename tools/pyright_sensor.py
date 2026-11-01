#!/usr/bin/env python3
"""Type-check sensor: run pyright and print a sensors sidecar `default` parser reading.

Each rule that fired carries its self-correction text from tools/guidance/pyright.json (rules
without an entry get the `default` one). Always exits 0; the reading's `success` carries the
result.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SEVERITY = {"error": "error", "warning": "warning", "information": "info"}
GUIDANCE = json.loads((Path(__file__).parent / "guidance" / "pyright.json").read_text("utf-8"))


def guidance(findings: list[dict]) -> list[dict]:
    """One block per rule that fired, in first-seen order."""
    rules = dict.fromkeys(f["rule"] or "default" for f in findings)
    return [{"rule": rule, "body": GUIDANCE.get(rule, GUIDANCE["default"])} for rule in rules]


def finding(diagnostic: dict) -> dict:
    start = diagnostic.get("range", {}).get("start", {})
    return {
        "file": os.path.relpath(diagnostic.get("file", "")),
        "line": start.get("line", 0) + 1,
        "column": start.get("character", 0) + 1,
        "rule": diagnostic.get("rule"),
        "message": diagnostic.get("message", ""),
        "severity": SEVERITY.get(diagnostic.get("severity", "error"), "error"),
    }


def reading(stdout: str, stderr: str) -> dict:
    try:
        report = json.loads(stdout)
    except ValueError:
        message = stderr[:500] or stdout[:500] or "pyright produced no output"
        return {
            "success": False,
            "summary": "pyright did not produce JSON",
            "findings": [{"message": message, "severity": "error", "rule": "pyright-crash"}],
        }
    errors = report.get("summary", {}).get("errorCount", 0)
    findings = [finding(d) for d in report.get("generalDiagnostics", [])]
    return {
        "success": errors == 0,
        "summary": f"{errors} type errors" if errors else "No type errors",
        "score": {"value": errors, "direction": "less", "description": "Pyright errors"},
        "findings": findings,
        "guidance": guidance(findings),
    }


def main() -> int:
    pyright = Path(sys.executable).parent / "pyright"
    result = subprocess.run(
        [str(pyright), "--outputjson"], capture_output=True, text=True, check=False
    )
    print(json.dumps(reading(result.stdout, result.stderr), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
