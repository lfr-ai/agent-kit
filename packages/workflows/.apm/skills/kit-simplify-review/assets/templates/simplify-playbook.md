# Simplify playbook

Use for a simplification that takes more than one reviewable step. Each stage
ends with evidence; do not start the next stage until it exists.

## 1. Frame

- Scope: `<diff, module or feature path>`
- User-visible outcome that must not change:
- Invariants (outputs, error types, messages callers parse, telemetry names):
- Maintenance cost being removed, in one sentence:

## 2. Inventory and findings

- [ ] Abstractions, options, flags and dependencies listed with call-site and
  variant counts
- [ ] Each lens applied; findings recorded in the finding report
- [ ] Each finding classified: delete, inline, replace, narrow or keep

## 3. Protect

- [ ] Characterization tests added where invariants were not pinned
- [ ] Baseline test, lint and benchmark results recorded

## 4. Cut, one finding per step

For each step:

- [ ] Change made in isolation
- [ ] Focused tests and package suite pass
- [ ] Observable outputs compared with the baseline
- [ ] Debt marker added if a deliberate limit was accepted

## 5. Verify and hand off

- [ ] Ledger regenerated; collector exits 0 for the touched paths
- [ ] Removed dependencies gone from manifests and lockfiles
- [ ] Report lists cuts made, findings kept and why, and follow-ups

## 6. Watch after release

- [ ] Error rates and latency for the touched paths checked against the
  baseline for an agreed period
- [ ] Revert plan for each step still valid until the watch period ends

## Evidence

- Finding report with ranked one-line findings
- Test and benchmark commands with results before and after
- Ledger diff
- Owner approval for any contract change
