# Evidence reporting

A completion claim is only as good as the evidence behind it. Report what ran,
what it proves, what failed and what was not checked, in a form someone else
can repeat.

## What to record per check

- **Exact command and working directory**, copied from what actually ran, not
  retyped from memory.
- **Environment**: OS, interpreter and key tool versions (or "versions from
  lockfile at revision X").
- **Revision and tree state**: commit plus whether the tree was dirty.
- **Result**: exit status and a one-line summary (`43 passed`,
  `2 findings in src/app/x.py`).
- **What a pass proves** and, as importantly, what it does not.

The gate script can emit this as JSON (`--report gate-report.json`); the
[gate report template](../assets/gate-report.md.template) turns it into a
human-readable hand-off, and the shorter [handoff record](../assets/evidence.md.template)
suits small changes.

## Statuses mean different things

| Status | Meaning | Counts as pass? |
| --- | --- | --- |
| passed | ran to completion, no findings | yes, for its scope |
| failed | ran and found problems | no |
| unavailable | tool, service or credential missing | no - report it |
| timeout | did not finish | no |
| skipped | deliberately not run | no - give the reason |
| inspected | read by a person, not executed | no - label it as review |

Never fold `unavailable`, `skipped` or `inspected` into "all green".

## Behavioral evidence

Gate results show the tree is clean; behavioral evidence shows the change
works:

1. The original symptom or requested behavior, reproduced before the change
   (red) and shown fixed after it (green), with the same command.
2. The highest-risk negative case (invalid input, failure path, permission
   denied) exercised.
3. Recovery or rollback exercised where the change touches state.

## Classifying failures in a full gate

When the full gate fails after a focused change, classify each failure before
acting:

- **Caused** by the change: fix it.
- **Coupled**: a test or contract that legitimately depends on the changed
  behavior; update it deliberately and explain why.
- **Pre-existing**: fails without the change too (prove it by running on the
  base revision). Report it with its diagnostic; do not fix unrelated issues
  silently, and do not hide them.

## Writing the summary

- Lead with the outcome and the evidence that proves it.
- List exact commands with results, in run order.
- State limitations plainly: what was not run and why, which platforms or
  live systems were not exercised.
- Do not claim runtime behavior (deployed service, IDE integration, cloud
  resource, model response) from static checks or unit tests.
- Keep sensitive data out: no tokens, no full environment dumps, no customer
  data in logs pasted into reports.

## Sources

- pytest, [Exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html)
- pytest, [Managing pytest's output](https://docs.pytest.org/en/stable/how-to/output.html)
- GitHub, [Workflow syntax for GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
