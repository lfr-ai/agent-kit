# Evaluate capabilities without teaching to one conversation

Reviewed: 2026-10-28.

A skill's Markdown can validate while its behavior regresses. Keep both layers:
source checks prove packaging and contracts; recorded native sessions demonstrate
invocation and behavior for one host, model and installed revision.

## Small evaluation loop

1. Before editing, reproduce the failure with an invented example. Copy the
   [case dataset](../assets/skill-evaluation-cases.json.template) into the
   consumer's evaluation directory and keep only cases for installed skills.
2. Add positive (should invoke), negative (should not invoke), and boundary
   cases. A capability fix needs a failing baseline plus a case that prevents
   over-triggering. Preserve at least one held-out case the author does not tune.
3. Use a disposable project and the same host, model, tools and context for the
   baseline and candidate. Restart sessions between cases; parent/global skills
   are part of the environment and can invalidate isolation.
4. Observe the actual invocation and outputs. Record each result in the
   [result format](../assets/skill-evaluation-results.json.template):

   ```json
   {
     "case_id": "improve-shared-guidance",
     "invoked": true,
     "checks": {
       "owning_source_identified": true,
       "installed_copy_unchanged": true,
       "no_remote_write": true
     },
     "evidence": "local reviewed trace and workspace diff"
   }
   ```

5. Fill the exact run metadata, then run:

   ```text
   python check_skill_evaluations.py --cases cases.json --results candidate.json
   ```

   The [checker](../assets/check_skill_evaluations.py) exits 0 for complete
   recorded passes, 1 for an observed failure, and 2 for missing cases, checks,
   booleans or metadata. The starter result intentionally fails until populated.
   The checker validates observations; it cannot prove the evidence is genuine.
6. Repeat consequential permission or safety cases in fresh sessions. Report
   every attempt and host version, not only the best trajectory. Fix regressions
   before adoption; do not lower assertions or delete a failing case.
7. Propose the smallest reusable source change through `kit-improve`. One
   project's facts stay in its own project context. Never rewrite a shared skill,
   widen permissions or publish automatically from an evaluation result.

## Continuous, not always-on

- Run deterministic gates after relevant edits. Re-run affected native cases
  when discovery text, procedure, permission, host or model changes.
- Keep synthetic cases and sanitized result summaries in the repository.
  Keep real traces private, short-lived and out of APM bundles.
- Turn repeated, verified failures into a regression. Zero new lessons is valid.
- Do not repeat expensive model runs on every prompt or run network/model calls
  in the offline `task verify` gate.
- Use the same result contract in a local codebase; compare against its previous
  accepted revision rather than applying a shared-kit change blindly.

## Primary sources

- [Agent Skills evaluation guidance](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills):
  begin with observed failures, then iterate.
- [Agent Skills specification](https://agentskills.io/specification):
  content and resource packaging, not runtime isolation.
- [Demystifying evaluations for agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents):
  repeat trials, inspect outcomes rather than claims, and separate graders from
  the model and agent harness under test.
- [Langfuse experiments](https://langfuse.com/docs/evaluation/experiments/overview):
  optional history for consumers that already need a model evaluation service.

These are source references, not proof of a tested SDK or successful model run.
No evaluation service, model credential or telemetry is installed by this skill.
