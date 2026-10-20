---
name: kit-simplify-review
description: Use when proposing a simplification that reduces maintenance cost while preserving required behavior and observability.
license: MIT
---

# Review for over-engineering and simplify safely

The question is not "is this code good?" but "what can be removed or replaced
with something smaller that the team already trusts, without changing required
behavior?". Correctness, security and style reviews are separate passes.

## Procedure

1. **Fix the scope.** Review a diff, one module or one feature path. Write the
   user-visible outcome and the invariants that must survive (outputs, error
   semantics, logs and metrics other people depend on).
2. **Inventory what exists.** List the abstractions in scope: classes,
   interfaces, factories, plugins, configuration keys, flags, wrappers,
   dependencies and generic helpers. For each, count real call sites and real
   variants (implementations, configured values) with a text search or an
   import graph.
3. **Apply the lenses** in [review lenses](references/review-lenses.md): YAGNI,
   native first, speculative abstraction, dead flexibility, indirection
   without payoff, defensive code for impossible states, and dependency weight.
   Record a finding only with evidence (a count, a path, a missing caller).
4. **Find the native replacement** for anything reinvented, using the
   [native-first catalogue](references/native-first.md). Prefer, in order: no
   code, the language standard library, the platform or framework already in
   use, an existing project helper, a new small function, a new dependency.
5. **Classify each finding** as `delete`, `inline`, `replace`, `narrow` (cut
   unused options) or `keep` with a reason. A `keep` is valid when the
   flexibility has a dated, owned need; record it as debt instead of arguing.
6. **Write one line per finding** in the
   [finding report](assets/finding-report.md.template):
   `path:line - cut <what> - replace with <what> - evidence <count or caller>`.
   Rank by maintenance cost removed, not by line count.
7. **Protect behavior before cutting.** For each accepted finding, make sure a
   test pins the invariant from step 1; add a characterization test first if
   none exists. Then make the cut in its own reviewable step.
8. **Verify.** Run the focused tests, the package suite and linters. Compare
   observable outputs (responses, logs, metrics names) before and after.
9. **Ledger the deliberate shortcuts.** Where you choose a simpler but limited
   solution on purpose, mark it with a debt comment and refresh the ledger with
   the [collector](assets/collect_debt_markers.py), following
   [the debt ledger guide](references/debt-ledger.md).
10. **Hand off** with the report, the test evidence and the ledger diff. Use the
    [simplification playbook](assets/templates/simplify-playbook.md) for
    multi-step simplifications.

## Collector usage

```text
python assets/collect_debt_markers.py src tests --as-of 2026-06-01 --require-owner --output docs/debt-ledger.md
```

The collector matches `DEBT` and `SHORTCUT` after a comment leader, writes a
Markdown table sorted by path and line, and prints `path:line: message` for
markers without a reason, without an owner (with `--require-owner`), with an
invalid date, or past their revisit date (with `--as-of`). It exits 1 on
findings and 2 on unusable input. Configure with `--marker`, `--ext`,
`--all-files` and `--exclude`; run `--self-test` after editing it.

## Acceptance gates

- [ ] Every finding cites evidence: call-site count, variant count, unused
      option, or the native facility that replaces it.
- [ ] Every cut is covered by a test that would fail if required behavior
      changed; error types, messages relied on by callers, and telemetry names
      are unchanged unless the owner agreed.
- [ ] No public contract widened or narrowed without a version note.
- [ ] Removed dependencies are removed from manifests and lockfiles in the
      same change; added dependencies are justified against the native option.
- [ ] Deliberate shortcuts carry debt markers with reason, owner and revisit;
      the collector exits 0 for the touched paths.
- [ ] The report ranks findings and states what was intentionally kept.

## Do not

- Simplify by deleting tests, logging, input validation or retries that guard
  real failure modes; those are behavior.
- Replace explicit code with a clever one-liner that the team cannot debug.
- Mix simplification with feature work in one diff.
- Chase a metric (lines, complexity score) without a maintenance argument.

Gates, failure modes and recovery steps are in the
[review guide](references/guide.md).
