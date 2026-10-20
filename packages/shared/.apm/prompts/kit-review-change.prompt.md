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

1. Collect the diff and read every changed hunk with enough surrounding code
   to understand callers and invariants.
2. State the intent of the change in one sentence; if the intent is unclear,
   say so and review against the most likely reading.
3. Check correctness: logic errors, off-by-one, null or empty handling,
   error paths that swallow failures, races, resource leaks.
4. Check contracts with [kit-consistency](../skills/kit-consistency/SKILL.md):
   renamed fields, changed defaults, status codes, and terminology that drift
   between producer, consumer, docs, and tests.
5. Check boundaries with
   [kit-hexagonal-architecture](../skills/kit-hexagonal-architecture/SKILL.md):
   inner layers importing frameworks, adapters leaking into the core.
6. Check tests with [kit-test-first](../skills/kit-test-first/SKILL.md): does a
   test fail without the change, are negative cases covered, are assertions
   weakened or deleted?
7. Check security basics: untrusted input reaching queries, shells, templates,
   or paths; secrets in code or logs; widened permissions.
8. For each candidate finding, confirm it by reading the code path. Drop it if
   you cannot construct a concrete failing input or scenario.
9. Note what you did not review (generated files, binaries, out-of-scope
   paths).

## Acceptance gates

- [ ] Every finding cites `path:line` and a concrete failure scenario.
- [ ] Style preferences and speculative refactors are excluded.
- [ ] Severity reflects user impact, not effort to fix.

## Output

Findings ordered by severity (`blocker`, `major`, `minor`), each with location,
problem, scenario, and suggested fix. Then "Verified OK" (areas checked with no
findings) and "Not reviewed". If there are no findings, say so plainly.
