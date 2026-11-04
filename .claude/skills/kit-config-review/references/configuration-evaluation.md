# Evaluate agent configuration changes

Instructions and skills can affect discovery, context use and task behavior.
Source checks verify repository contracts; they do not prove that a host loads
the content or that an agent performs better.

## Compare a change

1. Define measurable success and failure criteria before editing. Select
   representative positive, negative and boundary cases from the
   repository's `tests/evals/README.md`; add
   synthetic cases when existing coverage does not match the change.
2. Run deterministic checks for packaging and links:

   ```powershell
   task verify -- source
   task verify -- docs
   uv run --locked --no-sync python scripts/check_source.py --json
   ```

   Source character counts are only a size proxy. They are not token counts,
   proof of effective host context, or behavior measurements.
3. Compare the baseline and frozen candidate in fresh sessions using the same
   named host and version, model, tools, task inputs and effective
   customizations. Inspect actual outputs and workspace changes against the
   predefined criteria. Repeat consequential or nondeterministic cases, reserve
   held-out cases before tuning, and report every attempt.
   Choose trial counts and retry rules in advance. Keep OS/runtime, resource
   limits, time/token budgets and concurrency fixed; record exposed sampling
   settings. Separate task failures, infrastructure failures and disputed grader
   outcomes rather than retrying until a pass.
4. Keep a separate result file for every baseline and candidate trial.
   Record only observed results using the
   `kit-feedback-loop` observation contract in
   `packages/shared/.apm/skills/kit-feedback-loop/references/skill-evaluations.md`
   and validate the completed record:

   ```powershell
   uv run --locked --no-sync python packages/shared/.apm/skills/kit-feedback-loop/assets/check_skill_evaluations.py `
     --cases tests/evals/agent-kit.cases.json --results build/eval/candidate.json
   ```

   The checker enforces the record shape and completeness. It does not run an
   agent, verify that observations are genuine, or establish that a change
   improved performance.
5. Report the source and case revisions, host and version, model, tools,
   effective context, criteria, all results, and measured cost or latency.
   Separate structural checks, observed behavior and missing evidence.

## Boundaries

- APM installation, compilation, source validation and documentation checks
  establish delivery or structure, not live host behavior.
- Test behavior in each relevant native host; do not infer IDE discovery or
  runtime permissions from generated files.
- Use invented tasks and sanitized observations. Do not copy private traces,
  credentials or proprietary project facts into portable packages.
- Paid or account-using evaluations require explicit approval. Never promote
  unreviewed changes automatically or weaken graders to improve a score.

This approach follows the concise-skill guidance and measurable success
criteria in [Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
and [evaluation development guidance](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests).
