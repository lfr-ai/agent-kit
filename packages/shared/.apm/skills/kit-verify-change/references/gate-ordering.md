# Gate ordering and check-only versus fix modes

## Order checks from fast and likely to fail to slow and expensive

A gate is a sequence, not a set. Order it so the most common failures surface
in seconds and expensive steps only run on code that already passes the cheap
ones:

| Order | Step | Typical time | Why here |
| --- | --- | --- | --- |
| 1 | Lockfile consistency | < 1 s | a stale lock makes every later result untrustworthy |
| 2 | Formatting (check) | seconds | most frequent, trivially fixable |
| 3 | Lint | seconds | catches bugs and style before tests run |
| 4 | Type check | seconds to a minute | contract errors across modules |
| 5 | Import/architecture contracts | seconds | dependency direction |
| 6 | Spelling, Markdown, config schema | seconds | docs and configuration are code too |
| 7 | Secrets scan (working tree) | seconds | must never reach a remote |
| 8 | Unit and property tests | seconds to minutes | behavior |
| 9 | Integration tests | minutes | real boundaries |
| 10 | Link check, full-history secrets scan, mutation tests | minutes, network | slow or flaky by nature; scheduled or pre-merge |

Rules:

- **Fail fast locally, keep going in CI.** Locally, stop at the first failure
  to shorten the loop. In CI, `--keep-going` so one run reports everything.
- **Slow does not mean optional.** Slow steps run in CI on every merge or on a
  schedule, and their failures block or page someone.
- **Same order everywhere.** The script that runs locally is the script CI
  runs ([`run_gate.py.template`](../assets/run_gate.py.template)).

## Check-only by default, fix as an explicit action

A check answers "is the tree acceptable?" without changing it. A fixer changes
files. Mixing them hides changes: a "check" that formats files can pass in CI
while the committed code was never formatted, and a reviewer never sees the
rewrite.

| Tool | Check-only | Fix |
| --- | --- | --- |
| Ruff formatter | `ruff format --check` | `ruff format` |
| Ruff linter | `ruff check` | `ruff check --fix` (review unsafe fixes separately) |
| markdownlint-cli2 | `markdownlint-cli2` | `markdownlint-cli2 --fix` |
| uv | `uv lock --check` | `uv lock` |
| pre-commit fixers | (run in CI with `--show-diff-on-failure`) | `pre-commit run --all-files` locally |

Workflow:

1. `run_gate.py --fix` locally: fixers rewrite, then every check runs.
2. Review the diff the fixers produced; commit it deliberately.
3. CI runs `run_gate.py` (check-only). A fixer-only difference fails CI with a
   clear message instead of being silently applied.

Never put a fixer inside a step named or documented as a check, and never let a
gate regenerate tracked outputs (lockfiles, generated code, snapshots) as a
side effect; regeneration is a separate, reviewed command.

## Selecting steps

```text
python scripts/run_gate.py --list
python scripts/run_gate.py                       # fast + test tiers, stop at first failure
python scripts/run_gate.py --keep-going --report gate-report.json
python scripts/run_gate.py --only lint --only types
python scripts/run_gate.py --skip spelling       # say why in the evidence report
python scripts/run_gate.py --include-slow        # adds integration tests and link checks
```

An unavailable tool is reported as `unavailable` and fails the gate; it is
never counted as a pass. A timeout is its own status so hung steps are visible.

## Scoping to a change

While iterating, run the narrowest relevant check (one test file, one
directory for lint). Before claiming completion, run the full declared gate
after the last edit; partial runs are evidence for the part they covered only.

## Sources

- Ruff, [The Ruff formatter](https://docs.astral.sh/ruff/formatter/)
  and [The Ruff linter](https://docs.astral.sh/ruff/linter/)
- uv, [Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- pre-commit, [documentation](https://pre-commit.com/)
- pytest, [Exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html)
