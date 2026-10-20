# Quality gates and failure modes

Use this guide when reviewing a change folder that someone else drove, or when
auditing a set of archived changes. Stage detail lives in the per-stage
references linked from [the lifecycle overview](lifecycle.md).

## Review gates

| Gate | Pass condition | Typical evidence |
| --- | --- | --- |
| Scope | Proposal has why, what, non-goals, impact, rollback, owner acceptance | Review link with date |
| Testability | Every active requirement has a normative statement and a scenario with When and Then | Checker exit 0 |
| Coverage | Every proposal bullet maps to a requirement; every requirement maps to a task | Checker exit 0 with `--trace` |
| Progress honesty | Ticked boxes carry evidence that still reproduces | Re-run of the cited test |
| Proof | Every scenario has a verification row at an identified revision | `verification.md` |
| History | Living spec diff equals the change's requirement delta | Archive commit diff |

## Failure modes

- **Scope drift.** Tasks appear that no requirement cites. Detect with
  `--trace` reversed by hand: read each task and name its requirement. Fix by
  adding a requirement through the update operation, or by moving the task to
  a follow-up change.
- **Scenario theatre.** Scenarios restate the requirement ("Then it exports")
  and no test can fail them. Fix by rewriting with concrete values and an
  observable result.
- **Stale ticks.** Boxes ticked weeks ago whose evidence no longer passes after
  rebases. Fix with the continue operation: re-run and clear the box on failure.
- **Silent scope changes.** Requirements edited after acceptance without a
  **History** entry. Fix by restoring the accepted text and running update.
- **Archive drift.** Living specs edited directly, bypassing changes, so the
  archive no longer explains current behavior. Fix by opening a change that
  documents the edit retroactively, with verification evidence.
- **Placeholder leakage.** Template markers survive into review. The checker's
  marker rule catches `TODO`, `TBD`, `FIXME` and `XXX`; extend it with
  `--marker` for project-specific placeholders.

## Negative cases the checker must reject

- A requirement heading with no scenarios, or a scenario without `Then`.
- A task list written as plain bullets or numbered items.
- `Status: verified` with one unchecked box or without `Result: pass`.
- A removed requirement without a `Reason:` line.
- Two requirements with the same identifier.

The checker's `--self-test` exercises these cases; rerun it after any edit.

## Recovery

1. Run the checker and fix findings in file order; later findings often
   disappear once requirements parse correctly.
2. If a fix would weaken a requirement, stop and run update with the owner.
3. If evidence cannot be reproduced, clear the task's box, record why in
   **History**, and return to Apply.

## Prerequisites

- Python 3.11 or newer to run the checker; no third-party packages.
- Read access to the change folder and the living specs.
- An agreed `<changes-root>` and `<specs-root>` in the consumer's contributing
  guide.

## Assets

- [Proposal template](../assets/proposal.md.template)
- [Requirements template](../assets/requirements.md.template)
- [Design template](../assets/design.md.template)
- [Tasks template](../assets/tasks.md.template)
- [Verification template](../assets/verification.md.template)
- [Stage playbook](../assets/templates/spec-stage-playbook.md)
- [Change folder checker](../assets/check_spec_change.py)

## Sources

- [RFC 2119: Key words for use in RFCs](https://www.rfc-editor.org/rfc/rfc2119)
- [Gherkin reference](https://cucumber.io/docs/gherkin/reference/)
- [Python argparse documentation](https://docs.python.org/3/library/argparse.html)
