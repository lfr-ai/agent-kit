# Capability evaluations

[agent-kit.cases.json](agent-kit.cases.json) applies the existing
[observation contract](../../packages/shared/.apm/skills/kit-feedback-loop/references/skill-evaluations.md)
to this repository and its portable packages. Cases are invented inputs, not
observed passes.

1. Select the affected skills in a disposable project. Record source and dataset
   hashes, host version, model, tools and effective global customizations.
2. Run baseline and candidate in fresh sessions under the same conditions.
   Record actual invocations and every check; keep sanitized evidence locally.
3. Use the existing
   [result template](../../packages/shared/.apm/skills/kit-feedback-loop/assets/skill-evaluation-results.json.template),
   then validate each run:

   ```powershell
   uv run --locked --no-sync python packages/shared/.apm/skills/kit-feedback-loop/assets/check_skill_evaluations.py `
     --cases tests/evals/agent-kit.cases.json --results build/eval/candidate.json
   ```

Missing observations fail; never populate results from expected answers.
For optimization, reserve additional unseen tasks before tuning and evaluate
them only after the candidate is frozen.

The checker validates record shape and completeness; it does not run an agent,
verify the authenticity of observations or establish that a candidate improved.
Run cases in the relevant named host and version, and report the model, tools,
effective customizations and all results.
