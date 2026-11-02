#!/usr/bin/env python3
"""Lint sensor: ruff's JSON report plus self-correction guidance for the rules that fired.

Prints ruff's `--output-format json` array with one extra trailing object,
`{"sensors_rule_guidance": {"rules": {...}, "triggered": [...]}}`, which the sidecar's `ruff`
parser turns into guidance blocks. The text lives in tools/guidance/ruff.json; a code without
its own entry gets its family's (F, E, B, SIM, RUF, PERF). Only rules that fired are shipped, so a
clean run prints no advice. Exits with ruff's exit code.

Usage: python tools/ruff_sensor.py PATH [PATH ...]
"""

import json
import re
import subprocess
import sys
from pathlib import Path

GUIDANCE = json.loads((Path(__file__).parent / "guidance" / "ruff.json").read_text("utf-8"))
SUPPRESSION_KEY = "suppression"


def guidance_key(code: str) -> str | None:
    """The guidance entry for a ruff code: its own, else its family's, else None."""
    if code in GUIDANCE:
        return code
    family = re.match(r"[A-Z]+", code)
    return family[0] if family and family[0] in GUIDANCE else None


def guidance_block(diagnostics: list[dict]) -> dict:
    keys = (guidance_key(d.get("code") or "") for d in diagnostics)
    triggered = [*dict.fromkeys(key for key in keys if key), SUPPRESSION_KEY]
    return {
        "rules": {key: {"guidance": GUIDANCE[key]} for key in triggered},
        "triggered": triggered,
    }


def main(paths: list[str]) -> int:
    ruff = Path(sys.executable).parent / "ruff"
    command = [str(ruff), "check", "--output-format", "json", *paths]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        diagnostics = json.loads(result.stdout)
    except ValueError:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode or 2
    if diagnostics:
        diagnostics.append({"sensors_rule_guidance": guidance_block(diagnostics)})
    print(json.dumps(diagnostics, indent=2))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
