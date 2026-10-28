---
description: Review a diff for correctness, contract, boundary, and test defects and report only high-confidence findings with file and line evidence.
argument-hint: What to review, e.g. staged changes, a branch, a commit, or paths
agent: ask
---

# Review a change for real defects

Find defects a maintainer would want fixed before merge. Prefer a short list of
proven problems over a long list of opinions. Do not edit files.

## Input

- The user-supplied argument names the review target: staged changes, a
  branch compared to its base, a commit range, or specific paths. When it is
  empty, review the uncommitted working-tree changes.

## Procedure

1. Record the review target, base/head revisions and working-tree state.
   Include staged, unstaged and untracked changes when that is the requested
   scope; a branch review uses its actual merge base, not an assumed branch tip.
2. Read every changed hunk and follow risk-relevant callers, invariants and
   repository instructions. State exclusions; file selection is not evidence
   that unchanged consumers are unaffected.
3. State the intended outcome and acceptance criteria. Separate facts from
   assumptions; if missing intent changes the verdict, report the ambiguity
   instead of inventing a requirement.
4. Check correctness: logic errors, off-by-one, null or empty handling,
   error paths that swallow failures, races, resource leaks.
5. Check contracts with [kit-consistency](../skills/kit-consistency/SKILL.md):
   renamed fields, changed defaults, status codes, and terminology that drift
   between producer, consumer, docs, and tests.
6. Check boundaries with
   [kit-hexagonal-architecture](../skills/kit-hexagonal-architecture/SKILL.md):
   inner layers importing frameworks, adapters leaking into the core.
7. Check tests with [kit-test-first](../skills/kit-test-first/SKILL.md): does a
   test fail without the change, are negative cases covered, are assertions
   weakened or deleted?
8. Check security basics: untrusted input reaching queries, shells, templates,
   or paths; secrets in code or logs; widened permissions.
9. Challenge each candidate with a concrete failing input or scenario and
   evidence against it. Distinguish introduced defects from pre-existing behavior;
   retain tightly coupled issues but label them accurately.
10. Consolidate duplicate symptoms of one cause. Report impact, confidence and
    the smallest useful changed-line location, not a quota of findings.
11. Inspect supplied check results and their revision. Passing checks do not
    disprove an untested failure. Request missing execution evidence from the
    coordinator; this read-only review does not grant shell or delegation.
12. For a revised patch, check the original finding, its regression and new
    interactions. Mark resolved findings explicitly; do not repeat stale comments.

Use the [evidence-driven review guide](../skills/kit-feedback-loop/references/review.md)
for risk-based depth, specialist routing and review-quality feedback.

## Acceptance gates

- [ ] Every finding cites `path:line` and a concrete failure scenario.
- [ ] Style preferences and speculative refactors are excluded.
- [ ] Severity reflects user impact, not effort to fix.
- [ ] Findings are deduplicated and uncertainty and unavailable checks are explicit.

## Output

Findings ordered by severity (`blocker`, `major`, `minor`), each with location,
problem, scenario, confidence and suggested fix. Then "Checked with no findings"
(inspection is not executed verification) and "Not reviewed". If there are no
findings, say so plainly; this is not merge authorization or proof of correctness.
