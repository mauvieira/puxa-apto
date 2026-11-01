"""Acceptance tests for tools/code_shape.py, the ratchet that gates the Stop hook."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "code_shape.py"


def function(lines: int, header: str = "def f():") -> str:
    """A function spanning `lines` counted lines with a single statement."""
    items = "".join("        1,\n" for _ in range(lines - 3))
    return f"{header}\n    return [\n{items}    ]\n"


def nested_ifs(depth: int) -> str:
    body = "".join(f"{'    ' * (level + 1)}if x > {level}:\n" for level in range(depth))
    return f"def f(x):\n{body}{'    ' * (depth + 1)}return x\n"


ELIF_CHAIN = "def f(x):\n    if x == 0:\n        return 0\n" + "".join(
    f"    elif x == {n}:\n        return {n}\n" for n in range(1, 6)
)

PADDED = (
    'def f():\n    """Docstring.\n\n' + "    more\n" * 8 + '    """\n'
    + "\n" * 10
    + "    # comment\n" * 10
    + "    return [\n" + "        1,\n" * 57 + "    ]\n"
)

CASES = {
    "60 lines is within the limit": (function(60), [], True),
    "61 lines is reported on the def line": (
        "import os\n\n\n" + function(61),
        [("function-lines", 4, "f: function-lines 61 exceeds 60")],
        False,
    ),
    "blank, comment and docstring lines are not counted": (PADDED, [], True),
    "an elif chain does not nest": (ELIF_CHAIN, [], True),
    "five nested ifs exceed nesting": (
        nested_ifs(5), [("nesting", 1, "f: nesting 5 exceeds 4")], False
    ),
    "self plus five params is fine": (
        "class A:\n    def m(self, a, b, c, d, e):\n        return a\n", [], True
    ),
    "six params exceed the limit": (
        "class A:\n    def m(self, a, b, c, d, e, g):\n        return a\n",
        [("params", 2, "A.m: params 6 exceeds 5")],
        False,
    ),
    "a ceiling above the actual value is stale": (
        function(65, "def f():  # sensors: function-lines=70 -- r"),
        [("ceiling-stale", 1, "f: function-lines is 65; lower the ceiling from 70 to 65")],
        True,
    ),
    "exceeding the ceiling is an error": (
        function(75, "def f():  # sensors: function-lines=70 -- r"),
        [("function-lines", 1, "f: function-lines 75 exceeds ceiling 70 (default 60)")],
        False,
    ),
    "a ceiling needs a reason": (
        function(70, "def f():  # sensors: function-lines=70"),
        [("suppression-reason", 1, "suppression without a reason")],
        False,
    ),
    "noqa without a reason is an error": (
        "x = 1  # noqa: B904\n", [("suppression-reason", 1, "suppression without")], False
    ),
    "noqa with a reason is fine": ("x = 1  # noqa: B904 -- why\n", [], True),
    "a hash inside a string is not a comment": (
        'x = "# noqa"\ny = "# sensors: bogus=1"\n', [], True
    ),
    "a file ceiling above the actual value is stale": (
        "# sensors: file-lines=450 -- r\n" + "x = 1\n" * 420,
        [("ceiling-stale", 1, "case.py: file-lines is 420; lower the ceiling from 450 to 420")],
        True,
    ),
    "an unknown directive key is malformed": (
        function(10, "def f():  # sensors: lines=70 -- r"),
        [("sensors-directive", 1, "unknown ceiling key")],
        False,
    ),
}


@pytest.mark.parametrize(("source", "expected", "success"), CASES.values(), ids=CASES.keys())
def test_code_shape(tmp_path, source, expected, success):
    (tmp_path / "case.py").write_text(source)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--shape", ".", "--reasons", "."],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    reading = json.loads(result.stdout)

    found = [(f["rule"], f["line"], f["message"]) for f in reading["findings"]]
    assert [(rule, line) for rule, line, _ in found] == [(r, n) for r, n, _ in expected]
    for (_, _, message), (_, _, fragment) in zip(found, expected, strict=True):
        assert fragment in message
    assert {f["file"] for f in reading["findings"]} <= {"case.py"}
    assert reading["success"] is success
    assert result.returncode == (0 if success else 1)
