# Simplify review guide

Quality gates, failure modes, negative cases and recovery for over-engineering
reviews. The lenses are in [review lenses](review-lenses.md), replacements in
[the native-first catalogue](native-first.md), and shortcut tracking in
[the debt ledger guide](debt-ledger.md).

## Quality gates

| Gate | Pass condition |
| --- | --- |
| Evidence | Each finding cites a count, a path or a native API, not an opinion |
| Behavior | Tests pin the invariants before the cut and pass after it |
| Contract | Public signatures, error types and telemetry names unchanged, or versioned with owner agreement |
| Dependencies | Removed packages leave manifests and lockfiles; added ones beat the native option in writing |
| Debt | Deliberate limits carry markers with reason, owner and revisit; the collector exits 0 |
| Reviewability | Each cut is a separate step that can be reverted alone |

## Failure modes

- **Behavior loss disguised as simplification.** A removed retry, timeout or
  validation was protecting a real failure. Detect by asking which incident or
  requirement introduced it (history and blame), and by testing the failure
  path before removing anything.
- **Performance regression.** The native facility is slower for the project's
  data sizes. Detect with a benchmark of the hot path at realistic sizes;
  keep the custom code with a marker if the gap matters.
- **Coupling increase.** Inlining an abstraction leaks a dependency into many
  callers. Detect with an import graph before and after; prefer keeping a
  boundary that tests substitute.
- **Churn without payoff.** Large renames and moves that reduce no complexity.
  Detect by stating the maintenance cost removed in one sentence; if you
  cannot, drop the finding.
- **Clever replacement.** A dense expression replaces readable code. Detect by
  asking a reviewer unfamiliar with the code to explain it.

## Negative cases

These look like over-engineering but usually are not:

- An interface with one production implementation and one test double for an
  external system.
- A configuration key that differs only in production.
- Compatibility code with an owner and a dated removal.
- Logging and metrics with known dashboards or alerts.

## Recovery

1. If a cut breaks behavior, revert that step alone; the per-step structure
   makes this cheap.
2. Add the missing characterization test that would have caught it, then retry
   the cut or reclassify the finding as `keep` with a debt marker.
3. If a performance regression appears after release, restore the previous
   implementation behind the same call sites and record the benchmark that
   justifies it.

## Prerequisites

- A passing baseline test suite for the scope under review.
- Ability to search the repository and deployment configuration for callers
  and configured values.
- Python 3.11 or newer to run the collector; no third-party packages.

## Assets

- [Finding report template](../assets/finding-report.md.template)
- [Simplification playbook](../assets/templates/simplify-playbook.md)
- [Debt marker collector](../assets/collect_debt_markers.py)

## Sources

- [Python unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Python timeit documentation](https://docs.python.org/3/library/timeit.html)
- [Git blame documentation](https://git-scm.com/docs/git-blame)
