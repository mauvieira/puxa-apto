---
name: refactor-tick
description: "One small behavior-preserving refactor driven by the sensors: pick the worst shape finding, ceiling, or baseline suppression and pay it down. Use when asked for a refactor tick, after finishing a task, or when sensors report shape issues."
---

# Refactor tick

One target per tick. Small, behavior-preserving, verified.

1. **Read the sensors.** Run `.sensors/cli.sh check .`. If the sidecar is not running, run
   `.venv/bin/python tools/code_shape.py --shape puxa_apto tools --reasons puxa_apto tools tests`
   directly.

2. **Pick exactly one target**, in this priority order:
   1. any `shape` error;
   2. the `# sensors:` ceiling with the largest actual/limit ratio;
   3. a `-- baseline:` `# pyright: ignore` or `# noqa`.

   Mutation survivors are not targets while mutation testing is parked (see AGENTS.md).

   Within a priority level, prefer targets in files the current task touched.

3. **Confirm green first.** `.venv/bin/python -m pytest -q -n auto` must pass before you edit.

4. **Refactor, preserving behavior.** Follow the guidance text the sensor printed for the rule:
   - extract only deep helpers: a self-contained subtask whose caller need not know how it works;
   - no conjoined helpers that must be read together, no pass-through parameters;
   - define special cases out of existence (defaults, normalize once at the boundary, lookup
     tables instead of if/elif chains);
   - guard clauses and early `continue`/`return` instead of nesting.

   Tests must pass **unchanged**. If a test needs editing, it is not a refactor: stop and report.

5. **Ratchet.** Lower the ceiling or suppression to exactly the new actual value, or delete it
   when the value is within the default limit. The `ceiling-stale` warning names the number.

6. **Re-check.** `.sensors/cli.sh check .` (or the direct commands: pytest, ruff, pyright,
   code_shape) must be green.

7. **Report** the target, the metric values before → after, and the files changed. Do not commit
   unless asked.
