# AGENTS.md

## What this is

`puxa-apto` is a CLI that scrapes apartment listings from Brazilian real-estate sites and keeps
a deduplicated CSV: `puxa-apto scrape -C buscas/<x>.json`. Usage, options and the search file
format are in [README.md](README.md).

## Commands

Run everything from the repo root with the project venv (Python 3.12.1 from `.python-version`).

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'

.venv/bin/python -m pytest -q -n auto      # offline tests, parallel
.venv/bin/ruff check puxa_apto tests tools # lint
.venv/bin/pyright                          # types
.venv/bin/python tools/code_shape.py --shape puxa_apto tools --reasons puxa_apto tools tests
```

`-n auto` goes on the command line only, never into `addopts`: mutmut runs pytest in-process
and xdist workers would break it.

## Sensors sidecar

The [sensors sidecar](https://github.com/birgitta410/sensors-cli) runs the checks below in the
background and gives you one agent-readable report. Always call it through `.sensors/cli.sh`:
on Fedora a bare `sensors` is lm_sensors, the hardware monitor.

```bash
.sensors/cli.sh start .         # at the start of a session
.sensors/cli.sh start --show .  # same, with a live dashboard
.sensors/cli.sh check .         # read the latest results (exit 0 = all green)
.sensors/cli.sh stop .
```

Start it at the beginning of a session and read `check` instead of running ruff, pyright or
pytest by hand. A Claude Code Stop hook (`.claude/settings.json` → `.sensors/check-hook.sh`)
blocks the end of a turn while a sensor fails and prints the report; it stays silent when the
sidecar is not running.

| runner | tool | role |
|---|---|---|
| `tests` | pytest `-n auto` | gates |
| `lint` | ruff | gates |
| `types` | pyright via `tools/pyright_sensor.py` | gates |
| `shape` | `tools/code_shape.py` | gates |
| `cov` | pytest-cov | informational |
| `mutation`, `mut_state` | mutmut via `tools/mutation_sensor.py` | parked (disabled) |

Mutation testing is **parked**: with the CLI tests as coverage, a cold run took an estimated
35–40 minutes. The measurements, the unit-tests-only speed-up, and the steps to revive it are in
the comment above `[tool.mutmut]` in `pyproject.toml`. Do not run or chase mutation results until
it is revisited.

The sidecar's socket lives at `<project>/.sensors/puxa-apto.sock`, and Linux caps socket paths
at 108 bytes. Keep worktrees at shallow paths or `start` fails.

## Code shape

`tools/code_shape.py` measures every function and file under `puxa_apto/` and `tools/`. The
thresholds follow Ousterhout's *A Philosophy of Software Design*: depth beats length, the
metrics trigger review rather than mechanical splitting, and a big file is fine when it is one
deep module.

| key | limit | measures |
|---|---|---|
| `function-lines` | 60 | lines from `def` to end, without blanks, comments, docstrings |
| `complexity` | 10 | radon cyclomatic complexity |
| `params` | 5 | parameters excluding `self`/`cls`, `*args`, `**kwargs` |
| `statements` | 40 | statements in the body, not counting nested defs' bodies |
| `nesting` | 4 | depth of `if`/`for`/`while`/`with`/`try`/`match` blocks (`elif` does not nest) |
| `file-lines` | 400 | the same line rules as `function-lines`, over the file |

### When `shape` fails

A finding is a prompt to review the design, not an order to split the code. Work through these
steps in order:

1. Read the guidance the sensor prints for the rule. It is specific to that metric.
2. Ask whether the code hides one design decision behind a simple interface (a deep module).
   Length alone is not a defect; a long function that reads top to bottom as one operation is
   often better than five fragments.
3. Restructure only when it lowers the complexity a reader must hold. Good moves: a
   self-contained subtask the caller need not understand, special cases defined out of existence
   (defaults, normalizing input once at the boundary, a lookup table instead of an if/elif
   chain), guard clauses instead of nesting, a dataclass for values that always travel together.
4. Do not split just to satisfy the number. Avoid shallow helpers that only forward their
   arguments, conjoined helpers that must be read together or pass state back and forth, and
   pass-through parameters. If the only split you can find is one of these, the code is better
   as it is.
5. In that case raise the ceiling with a reason a reviewer can check. A raised ceiling is the
   exception, and it stays visible in the diff.
6. Behavior must not change. Existing tests pass unchanged; if a test needs editing, it was not
   a refactor.

When a function genuinely reads best as one unit, raise its ceiling on the `def` line, and say
why:

```python
def scrape(  # sensors: complexity=14, params=8 -- typer command: parameters are the CLI surface
```

A file ceiling goes on its own comment line: `# sensors: file-lines=520 -- <the design decision
it hides>`.

Rules:

- Every `# noqa`, `# pyright: ignore`, `# type: ignore` and `# sensors:` needs ` -- <reason>`.
  The `shape` runner fails on a suppression without one.
- Ceilings are a ratchet. When the code improves, the sensor warns `ceiling-stale`; lower the
  ceiling to the new value or delete it, exactly as the message says.
- Ceilings and ignores marked `-- baseline:` predate the sensors. Pay them down with
  `refactor-tick`.

## Refactor cadence

After any task that changed `puxa_apto/`, run one `refactor-tick` (skill in
`.claude/skills/refactor-tick/`) on code the task touched: leave the area cleaner than you found
it. Also run one whenever the user asks. One target per tick.

## Testing

- The CLI behavior is covered by offline acceptance tests in `tests/test_scrape_cli.py`. They
  drive the real CLI through Typer's `CliRunner`; the `fake_sites` fixture in
  `tests/conftest.py` serves captured pages from `tests/fixtures/*.html.gz` instead of the
  network and patches out `time.sleep`. Prefer extending them for scraping and CLI behavior.
- The pure modules (`puxa_apto/utils/` except `web.py`, `search.py`, `models/`) also have fast
  unit tests (`tests/test_<module>.py`) through their public functions. Keep them in
  milliseconds.
- Mutation testing (parked, see above) covers exactly those pure modules. `web.py` is excluded
  because the tests replace it.

## Conventions

- English in code, comments and docs.
- Do not commit unless asked.
