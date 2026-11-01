#!/usr/bin/env python3
"""Code-shape sensor: size and complexity limits with inline, reasoned ceilings (a ratchet).

Prints one JSON reading in the sensors sidecar `default` parser schema and exits 1 when any
error is found. Limits follow Ousterhout's A Philosophy of Software Design: they trigger review,
they do not order mechanical splitting. A function or file may raise its own ceiling with
`# sensors: key=INT -- reason`; the ceiling must then track the actual value as it improves.

Usage: python tools/code_shape.py --shape PATH [PATH ...] --reasons PATH [PATH ...]
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional, Union

from radon.visitors import ComplexityVisitor

LIMITS = {
    "function-lines": 60,
    "complexity": 10,
    "params": 5,
    "statements": 40,
    "nesting": 4,
    "file-lines": 400,
}
FUNCTION_KEYS = ("function-lines", "complexity", "params", "statements", "nesting")
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]
DEF_STMTS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
BLOCK_NODES = tuple(
    getattr(ast, name)
    for name in ("If", "For", "AsyncFor", "While", "With", "AsyncWith", "Try", "TryStar", "Match")
    if hasattr(ast, name)
)
SUPPRESSION = re.compile(r"(noqa\b|pyright:\s*ignore|type:\s*ignore|sensors:)", re.IGNORECASE)
REASON = re.compile(r"--\s+\S")
DIRECTIVE_ITEM = re.compile(r"^([A-Za-z-]+)=(\S*)$")
DIRECTIVE_PREFIX = "sensors:"

GUIDANCE = {
    "function-lines": (
        "Over 60 lines is a prompt to look, not an order to split. Ousterhout: depth is more "
        "important than length. Extract only a self-contained subtask whose caller does not need "
        "to know how it works. Never create conjoined helpers that must be read together or that "
        "pass state back and forth. If the function reads well as one unit, raise its ceiling on "
        "the def line: `# sensors: function-lines=N -- <why it reads as one unit>`. Raising is "
        "the exception."
    ),
    "complexity": (
        "Too many paths to hold in your head. First try to define special cases out of "
        "existence: defaults instead of None checks, normalize input once at the boundary, a "
        "lookup table instead of an if/elif chain. Raise the ceiling only as a last resort, with "
        "a reason."
    ),
    "params": (
        "More than 5 parameters usually means values that travel together (make a dataclass) or "
        "pass-through variables (move the decision into the callee). Typer command functions are "
        "the exception: their parameters are the CLI surface, so ceiling them with that reason."
    ),
    "statements": (
        "Over 40 statements: the function probably mixes levels of abstraction. Look for a run of "
        "steps that forms one named, self-contained operation."
    ),
    "nesting": (
        "Deeper than 4: use guard clauses and early continue/return, or extract the innermost "
        "loop body into a function that returns a value."
    ),
    "file-lines": (
        "A file over 400 lines is fine if it is one deep module. Check cohesion: does everything "
        "here hide the same design decision? If yes, add `# sensors: file-lines=N -- <the "
        "decision it hides>`. If not, split by design decision, not by size."
    ),
    "ceiling-stale": (
        "The code improved. Lower or delete the ceiling exactly as the message says, so the "
        "ratchet keeps holding."
    ),
    "suppression-reason": (
        "Every `# noqa`, `# pyright: ignore`, `# type: ignore` and `# sensors:` needs ` -- "
        "<reason>` so the exception is visible and reviewable."
    ),
    "sensors-directive": (
        "Malformed ceiling. Syntax: `# sensors: key=INT[, key=INT] -- reason` on the def line "
        "(function keys) or on its own comment line (`file-lines`)."
    ),
}


@dataclass
class Comment:
    """One `#`-separated segment of a comment token."""

    line: int
    text: str
    own_line: bool


@dataclass
class SourceFile:
    path: str
    tree: ast.Module
    comments: list[Comment]
    counted: set[int]


@dataclass
class Target:
    path: str
    line: int
    name: str


@dataclass
class Report:
    findings: list[dict] = field(default_factory=list)
    ceilings: int = 0
    code_lines: int = 0
    max_complexity: int = 0
    max_function_lines: int = 0

    def add(self, severity: str, target: Target, rule: str, message: str) -> None:
        self.findings.append(
            {
                "file": target.path,
                "line": target.line,
                "severity": severity,
                "rule": rule,
                "message": message,
            }
        )


def python_files(paths: Iterable[str]) -> list[str]:
    found: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        candidates = [path] if path.is_file() else path.rglob("*.py")
        found.update(p for p in candidates if "__pycache__" not in p.parts)
    return sorted(os.path.relpath(p) for p in found)


def read_comments(source: str) -> tuple[list[Comment], set[int]]:
    """Comment segments via tokenize (so `#` in strings is ignored) and comment-only lines."""
    comments: list[Comment] = []
    own_lines: set[int] = set()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        own_line = tok.line.lstrip().startswith("#")
        if own_line:
            own_lines.add(tok.start[0])
        comments.extend(
            Comment(tok.start[0], segment.strip(), own_line)
            for segment in tok.string.split("#")[1:]
            if segment.strip()
        )
    return comments, own_lines


def docstring(node: ast.AST) -> Optional[ast.Expr]:
    if not isinstance(node, (ast.Module, ast.ClassDef, *FUNCTION_NODES)) or not node.body:
        return None
    first = node.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first
    return None


def counted_lines(source: str, tree: ast.Module, comment_lines: set[int]) -> set[int]:
    """Lines that count toward size: not blank, not comment-only, not inside a docstring."""
    lines = {number for number, text in enumerate(source.splitlines(), 1) if text.strip()}
    for node in ast.walk(tree):
        doc = docstring(node)
        if doc is not None:
            lines -= set(range(doc.lineno, (doc.end_lineno or doc.lineno) + 1))
    return lines - comment_lines


def load(path: str, report: Report) -> Optional[SourceFile]:
    source = Path(path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=path)
        comments, own_lines = read_comments(source)
    except (SyntaxError, tokenize.TokenError) as err:
        report.add("error", Target(path, 1, path), "parse-error", f"cannot parse: {err}")
        return None
    return SourceFile(path, tree, comments, counted_lines(source, tree, own_lines))


def iter_functions(node: ast.AST, prefix: str = "") -> Iterator[tuple[str, FunctionNode]]:
    """(dotted qualname, def node) for every function, nested ones included."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, DEF_STMTS):
            name = f"{prefix}{child.name}"
            if isinstance(child, FUNCTION_NODES):
                yield name, child
            yield from iter_functions(child, name + ".")
        else:
            yield from iter_functions(child, prefix)


def child_statements(node: ast.AST) -> Iterator[ast.stmt]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.stmt):
            yield child
        elif isinstance(child, (ast.excepthandler, ast.match_case)):
            yield from child_statements(child)


def statement_weight(stmt: ast.stmt) -> int:
    if isinstance(stmt, DEF_STMTS):
        return 1
    return 1 + sum(statement_weight(child) for child in child_statements(stmt))


def max_depth(stmts: Iterable[ast.stmt], depth: int) -> int:
    depths = (block_depth(s, depth) for s in stmts if not isinstance(s, DEF_STMTS))
    return max(depths, default=depth)


def block_depth(stmt: ast.stmt, depth: int) -> int:
    if not isinstance(stmt, BLOCK_NODES):
        return depth
    if isinstance(stmt, ast.If) and len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
        # an elif stays at its parent's depth
        return max(max_depth(stmt.body, depth + 1), block_depth(stmt.orelse[0], depth))
    return max_depth(child_statements(stmt), depth + 1)


def function_metrics(func: FunctionNode, counted: set[int]) -> dict[str, int]:
    args = [*func.args.posonlyargs, *func.args.args]
    params = len(args) + len(func.args.kwonlyargs)
    if args and args[0].arg in ("self", "cls"):
        params -= 1
    body = func.body[1:] if docstring(func) else func.body
    end = func.end_lineno or func.lineno
    return {
        "function-lines": sum(1 for n in counted if func.lineno <= n <= end),
        "complexity": ComplexityVisitor.from_ast(func).functions[0].complexity,
        "params": params,
        "statements": sum(statement_weight(stmt) for stmt in body),
        "nesting": max_depth(func.body, 0),
    }


def parse_directive(comment: Comment, path: str, report: Report) -> dict[str, int]:
    """Valid `key=INT` pairs of a `sensors:` segment; malformed items are reported."""
    spec = comment.text[len(DIRECTIVE_PREFIX) :].split("--", 1)[0]
    items = [item.strip() for item in spec.split(",") if item.strip()]
    target = Target(path, comment.line, path)
    if not items:
        report.add("error", target, "sensors-directive", "empty ceiling directive")
    values: dict[str, int] = {}
    for item in items:
        match = DIRECTIVE_ITEM.match(item)
        if not match or match.group(1) not in LIMITS:
            report.add("error", target, "sensors-directive", f"unknown ceiling key in {item!r}")
        elif not match.group(2).isdigit():
            report.add("error", target, "sensors-directive", f"ceiling {item!r} is not an integer")
        else:
            values[match.group(1)] = int(match.group(2))
    return values


def placement_errors(comment: Comment, values: dict[str, int], def_lines: set[int]) -> list[str]:
    """Function keys belong on a def line, `file-lines` on its own comment line."""
    errors = []
    on_def = comment.line in def_lines
    if not on_def and any(key in FUNCTION_KEYS for key in values):
        errors.append("function ceilings belong on the def line")
    if "file-lines" in values and (on_def or not comment.own_line):
        errors.append("file-lines belongs on its own comment line, not on a def or code line")
    return errors


def collect_ceilings(
    source: SourceFile, def_lines: set[int], report: Report
) -> tuple[dict[int, dict[str, int]], Optional[tuple[int, int]]]:
    """Ceilings by def line, plus the file ceiling as (line, value)."""
    found: dict[object, tuple[int, dict[str, int]]] = {}
    for comment in source.comments:
        if not comment.text.startswith(DIRECTIVE_PREFIX):
            continue
        values = parse_directive(comment, source.path, report)
        errors = placement_errors(comment, values, def_lines)
        target_key = "file" if "file-lines" in values else comment.line
        if values and target_key in found:
            errors.append("a second ceiling directive for the same target")
        for message in errors:
            target = Target(source.path, comment.line, source.path)
            report.add("error", target, "sensors-directive", message)
        if errors or not values:
            continue
        found[target_key] = (comment.line, values)
        report.ceilings += len(values)
    file_line, file_values = found.pop("file", (1, {}))
    file_ceiling = (file_line, file_values["file-lines"]) if file_values else None
    return dict(found.values()), file_ceiling


def check_metric(
    report: Report, target: Target, key: str, actual: int, ceiling: Optional[int]
) -> None:
    limit = LIMITS[key]
    name = target.name
    if ceiling is None:
        if actual > limit:
            report.add("error", target, key, f"{name}: {key} {actual} exceeds {limit}")
    elif actual > ceiling:
        message = f"{name}: {key} {actual} exceeds ceiling {ceiling} (default {limit})"
        report.add("error", target, key, message)
    elif actual <= limit:
        message = f"{name}: {key} is {actual}, within the default {limit}; delete the {key} ceiling"
        report.add("warning", target, "ceiling-stale", message)
    elif actual < ceiling:
        message = f"{name}: {key} is {actual}; lower the ceiling from {ceiling} to {actual}"
        report.add("warning", target, "ceiling-stale", message)


def check_shape(path: str, report: Report) -> None:
    source = load(path, report)
    if source is None:
        return
    functions = list(iter_functions(source.tree))
    by_def, file_ceiling = collect_ceilings(source, {f.lineno for _, f in functions}, report)
    for name, func in functions:
        metrics = function_metrics(func, source.counted)
        report.max_complexity = max(report.max_complexity, metrics["complexity"])
        report.max_function_lines = max(report.max_function_lines, metrics["function-lines"])
        ceilings = by_def.get(func.lineno, {})
        target = Target(path, func.lineno, name)
        for key in FUNCTION_KEYS:
            check_metric(report, target, key, metrics[key], ceilings.get(key))
    file_lines = len(source.counted)
    report.code_lines += file_lines
    line, ceiling = file_ceiling if file_ceiling else (1, None)
    check_metric(report, Target(path, line, path), "file-lines", file_lines, ceiling)


def check_reasons(path: str, report: Report) -> None:
    try:
        comments, _ = read_comments(Path(path).read_text(encoding="utf-8"))
    except (SyntaxError, tokenize.TokenError) as err:
        report.add("error", Target(path, 1, path), "parse-error", f"cannot tokenize: {err}")
        return
    for comment in comments:
        if SUPPRESSION.match(comment.text) and not REASON.search(comment.text):
            message = "suppression without a reason: add ' -- <why>'"
            report.add("error", Target(path, comment.line, path), "suppression-reason", message)


def metric(key: str, label: str, value: int, unit: Optional[str] = None) -> dict:
    entry = {"key": key, "label": label, "value": value, "direction": "less"}
    return {**entry, "unit": unit} if unit else entry


def reading(report: Report) -> dict:
    errors = sum(1 for f in report.findings if f["severity"] == "error")
    warnings = len(report.findings) - errors
    rules = dict.fromkeys(f["rule"] for f in report.findings if f["rule"] in GUIDANCE)
    return {
        "success": errors == 0,
        "summary": f"{errors} errors, {warnings} warnings" if report.findings else "No issues",
        "score": {
            "value": errors,
            "direction": "less",
            "description": "Shape violations and unexplained suppressions",
        },
        "findings": report.findings,
        "metrics": [
            metric("codeLines", "Code lines", report.code_lines, "lines"),
            metric("ceilings", "Raised ceilings", report.ceilings),
            metric("maxComplexity", "Max complexity", report.max_complexity),
            metric("maxFunctionLines", "Longest function", report.max_function_lines, "lines"),
        ],
        "guidance": [{"rule": rule, "body": GUIDANCE[rule]} for rule in rules],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Code-shape sensor (see module docstring).")
    parser.add_argument("--shape", nargs="+", required=True, help="paths to measure")
    parser.add_argument("--reasons", nargs="+", required=True, help="paths to scan for reasons")
    args = parser.parse_args(argv)
    report = Report()
    for path in python_files(args.shape):
        check_shape(path, report)
    for path in python_files(args.reasons):
        check_reasons(path, report)
    result = reading(report)
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
