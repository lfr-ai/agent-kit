# Evidence-driven change review

Reviewed: 2026-10-28.

## Purpose and scope

Find defects a maintainer should address, not reasons to rewrite a working
patch. Review complements tests and accountable human approval; it does not
grant execution, delegation or merge permission.

Record the target, base/head revisions, working-tree state, acceptance criteria
and applicable instructions. For branch reviews use the actual merge base.
Include untracked files when the requested scope includes new work; a plain
tracked-file diff is not that inventory. Ask the coordinator for evidence
unavailable to a read-only reviewer.

Read the complete changed patch and expand by risk: callers, producer/consumer
contracts, changed defaults, lifecycle, concurrency, persistence, authorization,
installation and rollback. Review generated behavior through its canonical
source and gates; do not infer safety from generated-file exclusion.

## Candidate to finding

1. Identify a violated requirement or invariant, not a stylistic preference.
2. Trace the concrete input, state and call path to an observable consequence.
3. Inspect evidence against it: guards, caller guarantees, platform semantics,
   tests, migration sequencing and documented compatibility.
4. Distinguish an introduced regression from a pre-existing or tightly coupled
   defect. Explain why the current patch is the appropriate remediation point.
5. Confirm the location and required conditions. If execution is unavailable,
   label the result as code-traced, not reproduced.
6. Merge repeated symptoms of one cause. Keep materially different failure
   paths distinct even if they occur on the same line.
7. Report severity by impact and likelihood, confidence by strength of evidence.
   Do not inflate either because multiple reviewers repeated the same claim.
8. Give the smallest useful fix direction and regression, without prescribing
   an unnecessary abstraction or editing the patch during review.

Use the existing checklist's finding table. A useful finding includes location,
scenario, impact, evidence, uncertainty and disposition. "Could be cleaner" or
"might fail" without a reachable scenario is not a merge-blocking defect.
An unresolved intent or missing runtime prerequisite belongs in limitations,
not in invented certainty.

## Depth and independent review

Start with the existing deterministic checks and one focused reviewer.
The authorized coordinator can assign additional specialists when distinct
risks require substantial separate context: identity/inputs, architecture,
delivery, or a complex independent subsystem. Do not fan out by default.

Supply each reviewer the patch, intent, relevant contracts and check evidence.
Let specialists form their own conclusions before consolidating reports.
Return concise candidates with evidence, not exploration transcripts.
The coordinator challenges and deduplicates results; a vote is not verification.
Read-only roles remain read-only and do not spawn workers or run test commands.

The implementer self-check and independent review have different jobs:
self-check establishes task acceptance; independent review challenges the
assumptions, missing cases and interactions. Neither replaces the other.

## Re-review and feedback

For a fix, identify the new revision, reproduce or inspect the original
scenario, check its regression and inspect new interactions. Mark findings
resolved, still open, accepted with an accountable reason, or withdrawn after
contrary evidence. Old check output does not certify the revised patch.

Keep the existing loop budget. Stop when acceptance is evidenced and no
actionable in-scope findings remain; stop and report blockers when the budget,
permissions or prerequisites are exhausted. Never iterate solely to improve
a subjective numerical score or manufacture a finding.

On representative changes, record whether findings were confirmed, fixed,
rejected or missed later, alongside latency and cost if the host exposes them.
Use that evidence to tune scope, prompts and routing. Raw comment count and
acceptance of every suggestion are not quality metrics. Do not introduce a
telemetry service or send private patches to a hosted reviewer without approval.

## Primary sources

- [Anthropic: solving code review](https://claude.dev/blog/solving-code-review-at-anthropic/)
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices)
- [Google engineering review guidance](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
- [GitHub: responsible use of Copilot code review](https://docs.github.com/en/copilot/responsible-use/code-review)

Vendor case-study outcomes are not performance promises for another repository.
Check the current host documentation and account policy before adopting a
hosted review service or relying on a native capability.
