---
description: Run a bounded LLM experiment that compares models, prompt versions, temperatures or seeds on a fixed evaluation dataset and gates the result against a baseline.
argument-hint: Change or comparison to evaluate, e.g. "prompt v7 versus v6 on the support dataset"
agent: agent
---

# Run an LLM experiment

Compare candidate settings on one fixed, versioned dataset and decide with
evidence. An experiment compares settings; it never trains a model and never
changes the dataset mid-comparison.

## Input

- The user-supplied argument names the change or comparison. Ask for the
  dataset location and the approved cost budget if they are not in the
  repository; never build a dataset from production traces or personal data.

## Procedure

1. Load [kit-llm-evaluation](../skills/kit-llm-evaluation/SKILL.md) and follow
   its [experiments reference](../skills/kit-llm-evaluation/references/experiments.md).
2. Load the `kit-config` skill and read its `references/reproducible-experiments.md`;
   copy `experiment_config.py.template` and `experiment.json.template` from
   its assets if the project has no experiment planner.
3. Fix the dataset version and record its content fingerprint with the
   evaluation harness.
4. Declare the gating metrics, absolute floors, allowed regression and cost
   and latency ceilings before any run.
5. Define explicit finite axes (model alias, exact prompt version,
   temperature, seed), compute jobs times cases times repeats, and stop if
   the total exceeds the approved budget.
6. Plan jobs with the kit-config planner and write each manifest; never
   reuse an output directory.
7. Run the baseline and each candidate behind the model port, recording
   outputs as JSONL beside each manifest with the served model snapshot.
8. Score every job with the harness, including the baseline on the same
   dataset fingerprint; repeat cases when sampling is enabled.
9. Compare paired results, read confidence intervals and the minimum
   detectable difference, and inspect regressed cases by hand.
10. Confirm the selected candidate once on the held-out split and the
    safety slices.
11. Record the decision in the evaluation report worksheet; update the
    baseline only if the decision says so.

## Acceptance gates

- [ ] Every job reports dataset version and fingerprint, exact prompt
  version, model alias and served snapshot, temperature and seed.
- [ ] Gates were declared before the run; harness exit codes are reported.
- [ ] Differences below the minimum detectable difference are reported as no
  measurable change.
- [ ] Total spend stayed within the approved budget.
- [ ] No production personal data entered datasets, outputs or reports.

## Output

A results table (job, metric, mean, interval, delta versus baseline, gate,
result), cost and latency per job, the failure analysis, the exact commands,
and a recommendation to adopt, revise or reject.
