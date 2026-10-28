# Bounded self-review and feedback

Reviewed: 2026-10-28.

Check the requested outcome, repair evidenced defects and stop. Set the iteration
budget and early-stop condition before reviewing; more revisions are not a
quality measure. This guide owns self-review. Independent assessment, finding
verification and patch re-review belong to the [review guide](review.md).

## Establish the evidence

| Input | Use | Limit |
| --- | --- | --- |
| Acceptance criteria | Define observable success and failure cases | Missing or disputed intent is not permission to invent requirements |
| Governing policy and scoped instructions | Identify required conventions and approval boundaries | Prompt text does not enforce permissions |
| Deterministic checks | Test their declared contracts reproducibly | A pass does not prove untested behavior |
| Inspection with `path:line` and a failing scenario | Find gaps, interactions and incorrect assumptions | Label code-traced findings separately from executed reproductions |
| General preference | Optional proposal | Not a reason to block or iterate |

Run relevant deterministic checks before subjective review. When inspection
contradicts a pass, reproduce the scenario and identify the incorrect code, test
or requirement. Do not vote away the finding or weaken a valid assertion.

## Refresh only relevant context

Read the operating policy, matching instructions and relevant skill acceptance
gates at review start. Refresh them when scope or guidance changes, or context
has been lost; do not reload unchanged handbooks on every iteration.

Keep a short checklist of required rules and their proving checks. Consumer
conventions govern the review; examples below do not impose a new language-wide
style policy.

| Concern | Prefer the existing check | Inspect the remaining risk |
| --- | --- | --- |
| Naming and constants | Linter and convention checker | Meaning, units and the project's literal exceptions |
| API documentation | Project docstring/documentation checker | Changed arguments, errors and observable behavior |
| Typing | Configured type checker | Unvalidated dynamic boundaries or weakened guarantees |
| Layering | Import/architecture contracts | Policy ownership, dependency direction and I/O boundaries |
| Errors | Exception rules and negative tests | Actionable diagnostics, preserved causes and cleanup |
| Tests | Focused behavioral regressions | Original symptom, failure paths and assertions that prove the outcome |
| Docs and resources | Links, spelling and owning source contracts | Changed behavior, examples, ownership and installation |

## Simplify without losing behavior

1. Remove a helper, class, flag or configuration only after checking callers and
   required behavior. Passing tests alone do not prove unused or untested code
   is safe to delete.
2. Prefer the standard library, native platform or an already-locked dependency
   when it preserves the contract and handles the relevant edge cases.
3. Consult current primary documentation to resolve a concrete compatibility or
   support question. Check the version actually supported, not just the newest
   release; record the source and uncertainty.
4. Drop unrelated additions from your own patch. Do not revert another author's
   edits to make the scope appear clean.

An upgrade or new dependency is a separate reviewed change, not an automatic
consequence of finding newer documentation.

## Iterate or stop

| Evidence | Decision |
| --- | --- |
| Caused or coupled check failure | Fix the cause and rerun the affected check |
| Unmet criterion or cited required-rule violation | Repair within scope and budget; otherwise report the blocker |
| A simpler equivalent with preserved behavior | Simplify locally and rerun the affected checks |
| The same finding returns | Continue only with new evidence and budget; otherwise report the failed approach |
| Scope, permission or prerequisite is missing | Stop and report; do not fabricate success |
| Budget is exhausted | Stop and list remaining findings by impact |
| Criteria are evidenced and no actionable in-scope finding remains | Run final acceptance and hand off |
| Only preferences or a subjective score remain | Stop |

Fix correctness/security and contract risks first, then required conventions,
tests/docs and local simplification. Each iteration records the finding, change,
exact check result and criterion status in the existing iteration log.

The completion gate must run after the last relevant edit. Preserve thresholds,
assertions and approval rules; report failures and unavailable checks explicitly.
Do not claim native, cloud or model behavior from file tests.

Use COMPLETE only when required criteria and final gates are evidenced, ITERATE
when authorized in-scope work and budget remain, and BLOCKED when unmet work
cannot continue. Missing tools, unsupported host behavior or exhausted budget
do not make a required criterion not-applicable. Record actual provider,
host/harness and version for native claims; do not infer cross-provider parity.

## Retain useful feedback

Turn a reproducible escaped defect into a regression. Record a lesson through
`kit-project-memory` only when it is durable, evidenced and not already captured
by an existing rule or check. Zero new lessons is a valid outcome; transcripts
and transient task state do not belong in permanent memory.

## Primary sources

- [Claude Code best practices](https://code.claude.com/docs/en/best-practices)
- [Anthropic code review case study](https://claude.dev/blog/solving-code-review-at-anthropic/)
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Google SRE: postmortem culture](https://sre.google/sre-book/postmortem-culture/)
