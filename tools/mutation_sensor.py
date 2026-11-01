#!/usr/bin/env python3
"""Mutation-testing sensor around mutmut. Informational: its readings never fail the sidecar.

Subcommands:
  run      run mutmut (incremental), then print the `report` reading
  report   print a sensors sidecar `default` parser reading from the last mutmut results
  summary  print one plain-text line for the sidecar's `on_check` runner
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MUTMUT = str(Path(sys.executable).parent / "mutmut")
STATS = Path("mutants") / "mutmut-cicd-stats.json"
SURVIVOR = re.compile(r"^\s+(\S+): (survived|no tests)$")
MAX_SURVIVORS = 15


def mutmut(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([MUTMUT, *args], capture_output=True, text=True, check=False)


def load_stats() -> dict | None:
    """Export mutmut's stats and read them; None when there are no results yet."""
    if not STATS.parent.is_dir():
        return None
    mutmut("export-cicd-stats")
    return json.loads(STATS.read_text()) if STATS.exists() else None


def score(stats: dict) -> int:
    tested = stats["total"] - stats["skipped"]
    return round(100 * (stats["killed"] + stats["timeout"]) / tested) if tested else 0


def survivors() -> list[tuple[str, str]]:
    lines = mutmut("results").stdout.splitlines()
    return [(match[1], match[2]) for match in map(SURVIVOR.match, lines) if match]


def report() -> dict:
    stats = load_stats()
    if stats is None:
        return {"success": True, "summary": "No mutation results yet"}
    value = score(stats)
    findings = [
        {
            "severity": "warning",
            "rule": status,
            "message": f"{name}: inspect with .venv/bin/mutmut show {name}",
        }
        for name, status in survivors()[:MAX_SURVIVORS]
    ]
    metrics = [
        ("killed", "Killed", "killed", "more"),
        ("survived", "Survived", "survived", "less"),
        ("noTests", "Without tests", "no_tests", "less"),
        ("timeout", "Timed out", "timeout", "less"),
        ("total", "Total mutants", "total", "less"),
    ]
    return {
        "success": True,
        "summary": f"Mutation score {value}% ({stats['survived']} survived)",
        "score": {
            "value": value,
            "direction": "more",
            "description": "Mutation score (% of mutants killed)",
        },
        "metrics": [
            {"key": key, "label": label, "value": stats[stat], "direction": direction}
            for key, label, stat, direction in metrics
        ],
        "findings": findings,
    }


def run() -> dict:
    result = mutmut("run")
    if result.returncode == 0:
        return report()
    tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
    return {
        "success": False,
        "summary": f"mutmut run failed (exit {result.returncode})",
        "findings": [{"severity": "error", "rule": "mutmut-run", "message": tail}],
    }


def summary() -> str:
    stats = load_stats()
    if stats is None:
        return "No mutation results yet. Run .venv/bin/mutmut run"
    as_of = datetime.fromtimestamp(STATS.stat().st_mtime).isoformat(timespec="minutes")
    return (
        f"mutation {score(stats)}% ({stats['killed']} killed, {stats['survived']} survived, "
        f"{stats['no_tests']} without tests) as of {as_of}; "
        "list survivors: .venv/bin/mutmut results"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="mutmut sensor")
    parser.add_argument("command", choices=["run", "report", "summary"])
    command = parser.parse_args().command
    if command == "summary":
        print(summary())
    else:
        print(json.dumps(run() if command == "run" else report(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
