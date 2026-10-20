# Measuring complexity

Measure before and after a refactoring so "simpler" is a claim with evidence.
No single number decides; use several signals and read the code they point to.

## Signals

| Signal | What it measures | Typical use |
| --- | --- | --- |
| Cyclomatic complexity | number of independent paths through a function (decisions + 1) | lower bound on tests needed to cover branches |
| Cognitive complexity | how hard a function is to read; nesting costs more than sequence | finding functions people struggle with |
| Function length and parameter count | size and interface width | candidates for extract function or parameter object |
| Nesting depth | levels of nested blocks | candidates for guard clauses or split phase |
| Fan-in / fan-out | how many modules depend on / are depended on by a module | stability and blast radius of a change |
| Import cycles | modules that depend on each other transitively | layering violations |
| Churn | how often a file changes (commits touching it) | where effort is actually spent |
| Hot spots | churn multiplied by complexity | where refactoring pays off first |
| Duplication | cloned token sequences | candidates to triage, see [duplication](duplication.md) |

## Thresholds

Treat thresholds as review triggers, not goals:

- Cyclomatic complexity above about 10 per function deserves a look; above
  about 20 is usually hard to test exhaustively.
- More than about five parameters, or any boolean parameter that switches
  behavior, suggests a missing concept.
- Nesting deeper than three or four levels hurts readability.

Configure the limits in the repository's linter so they are checked the same
way in the editor and CI. In Python with Ruff, for example: `C901` with
`[lint.mccabe] max-complexity`, and the Pylint-derived `PLR0911` (returns),
`PLR0912` (branches), `PLR0913` (arguments) and `PLR0915` (statements). Other
ecosystems have equivalents (ESLint `complexity`, `max-depth`, `max-params`).

Avoid per-line suppressions as a way to pass the gate. A suppression needs a
reason a reviewer can evaluate.

## Hot spot analysis

Complexity alone points at old, stable code that nobody touches. Combine it with
churn:

1. Count changes per file over a meaningful window, for example:
   `git log --since=12.months --name-only --format= | sort | uniq -c | sort -rn`.
2. Measure complexity for the same files with the linter or a complexity tool.
3. Rank by churn times complexity; the top entries are where refactoring
   reduces future cost.
4. Read the top files. Confirm the metric matches a real problem (frequent
   defects, slow reviews, merge conflicts) before planning work.

## Before and after

For a refactoring that claims to simplify:

1. Record the metrics for the touched functions and modules before the first
   step (linter output, a complexity report, import graph).
2. Record them again after the last step.
3. Report both in the [behavior ledger](../assets/behavior.md.template) next to
   the unchanged behavioral evidence.

A refactoring that keeps behavior and does not move any metric may still be
worth it (better names, clearer boundaries), but say so explicitly.

## Pitfalls

- Splitting a complex function into many tiny ones with shared mutable state
  lowers per-function numbers and raises real complexity.
- Metrics on generated code, vendored code and tests distort rankings; exclude
  them.
- Optimizing a metric that nobody acted on is busywork. Tie each target to a
  cost: defects, review time, onboarding time.

## Sources

- [Ruff rule C901 (complex-structure)](https://docs.astral.sh/ruff/rules/complex-structure/)
- [Ruff settings: lint.mccabe](https://docs.astral.sh/ruff/settings/#lint_mccabe)
- [ESLint complexity rule](https://eslint.org/docs/latest/rules/complexity)
- [NIST SP 500-235: Structured Testing using the cyclomatic complexity metric](https://www.nist.gov/publications/structured-testing-testing-methodology-using-cyclomatic-complexity-metric)
- [git-log](https://git-scm.com/docs/git-log)
