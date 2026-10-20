# Duplication review guide

Quality gates, failure modes, negative cases and recovery for clone reviews.
Configuration lives in [jscpd configuration](jscpd-configuration.md), judgment
in [duplication versus coincidence](judging-clones.md), and fixes in
[extraction patterns](extraction-patterns.md).

## Quality gates

| Gate | Pass condition |
| --- | --- |
| Reproducible scan | jscpd version, configuration file and command recorded |
| Clean scope | Generated, vendored, build and snapshot paths excluded before judging |
| Reasoned decisions | Each clone above the agreed size has extract, generate, parameterize, keep or defer with a reason |
| Ownership | Extracted code has one owner and sits at the lowest common dependency |
| Structure | No new import cycle or upward dependency after extraction |
| Behavior | Tests pinning each former copy pass unchanged |
| Comparable re-scan | Identical configuration before and after |

## Failure modes

- **False positives from generated or vendored code.** Detect when clones point
  at files with generator banners, lockfiles or `dist` folders; exclude by
  path and re-scan before judging anything.
- **Fragmented reports.** One logical copy shows as several small clones
  because of small edits. Detect by sorting clones by file pair; judge the
  pair as a whole.
- **Over-sensitive settings.** Thresholds so low that imports, argument lists
  or framework boilerplate dominate. Raise `minTokens` before reviewing.
- **Hidden divergence.** Copies look identical but one has a bug fix the other
  lacks. Detect by diffing the two regions; decide which behavior is correct
  before unifying, and add a test for it.
- **Percentage dilution.** A large new file lowers the overall percentage while
  adding clones. Gate on per-clone size or new clones, not only on the total.

## Negative cases

- Two services each validating the same request field: unify through the
  contract (generation or contract test), not a shared module.
- Parallel migrations: keep; they are immutable history.
- Ten test functions with the same setup and different assertions: extract a
  builder, keep the tests separate.

## Recovery

1. If an extraction couples code that should be independent, revert it and
   record a `keep` decision with the reason.
2. If an extraction changes behavior, restore the copies, add the missing tests
   for the divergent case, then retry.
3. If a gate fails on legacy clones, switch the gate to new clones only
   (baseline or changed files) rather than raising the threshold.

## Prerequisites

- Node.js for `npx jscpd`, or another supported jscpd installation.
- Python 3.11 or newer for the summarizer; no third-party packages.

## Assets

- [jscpd configuration template](../assets/jscpd.json.template)
- [Report summarizer](../assets/summarize_jscpd_report.py)
- [Evidence worksheet](../assets/templates/duplication-evidence-template.md)

## Sources

- [jscpd repository and documentation](https://github.com/kucherenko/jscpd)
- [git diff documentation](https://git-scm.com/docs/git-diff)
