"""The guidance an agent reads when a sensor fails: right text, only for rules that fired."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
RUFF_GUIDANCE = json.loads((TOOLS / "guidance" / "ruff.json").read_text("utf-8"))
PYRIGHT_GUIDANCE = json.loads((TOOLS / "guidance" / "pyright.json").read_text("utf-8"))


def ruff_sensor(tmp_path: Path, source: str) -> tuple[int, list]:
    (tmp_path / "case.py").write_text(source)
    result = subprocess.run(
        [sys.executable, str(TOOLS / "ruff_sensor.py"), "case.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def test_a_failing_lint_ships_guidance_for_each_fired_rule_then_how_to_suppress(tmp_path):
    # F401 has its own entry; F632 (`is` with a literal) falls back to the F family's.
    code, report = ruff_sensor(tmp_path, 'import os\nimport sys\n\nx = 1\ny = x is "a"\n')

    *diagnostics, extra = report
    block = extra["sensors_rule_guidance"]
    assert code == 1
    assert sorted(d["code"] for d in diagnostics) == ["F401", "F401", "F632"]
    assert block["triggered"] == ["F401", "F", "suppression"]
    assert block["rules"] == {
        key: {"guidance": RUFF_GUIDANCE[key]} for key in ("F401", "F", "suppression")
    }


def test_a_clean_lint_prints_no_guidance(tmp_path):
    assert ruff_sensor(tmp_path, "x = 1\n") == (0, [])


def load_pyright_sensor():
    spec = importlib.util.spec_from_file_location("pyright_sensor", TOOLS / "pyright_sensor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def diagnostic(rule: str, line: int) -> dict:
    return {
        "file": "puxa_apto/x.py",
        "severity": "error",
        "message": "m",
        "rule": rule,
        "range": {"start": {"line": line, "character": 0}},
    }


def test_type_errors_carry_guidance_once_per_rule_with_a_default_for_unknown_rules():
    pyright_output = {
        "summary": {"errorCount": 3},
        "generalDiagnostics": [
            diagnostic("reportOptionalMemberAccess", 1),
            diagnostic("reportSomethingNew", 2),
            diagnostic("reportOptionalMemberAccess", 3),
        ],
    }

    reading = load_pyright_sensor().reading(json.dumps(pyright_output), "")

    assert reading["success"] is False
    assert reading["guidance"] == [
        {"rule": "reportOptionalMemberAccess",
         "body": PYRIGHT_GUIDANCE["reportOptionalMemberAccess"]},
        {"rule": "reportSomethingNew", "body": PYRIGHT_GUIDANCE["default"]},
    ]


def test_no_type_errors_means_no_guidance():
    reading = load_pyright_sensor().reading(
        json.dumps({"summary": {"errorCount": 0}, "generalDiagnostics": []}), ""
    )

    assert reading["success"] is True
    assert reading["guidance"] == []
