#!/usr/bin/env python3
"""Type-check sensor: run pyright and print a sensors sidecar `default` parser reading.

Always exits 0; the reading's `success` carries the result.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SEVERITY = {"error": "error", "warning": "warning", "information": "info"}


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
    return {
        "success": errors == 0,
        "summary": f"{errors} type errors" if errors else "No type errors",
        "score": {"value": errors, "direction": "less", "description": "Pyright errors"},
        "findings": [finding(d) for d in report.get("generalDiagnostics", [])],
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
