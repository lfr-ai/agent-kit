---
name: kit-llm-evaluation
description: Use when building or changing LLM evaluations - golden datasets, judges, statistics, CI gates, sweeps.
license: MIT
---

# Evaluate model-backed features with evidence

## Procedure

1. State the decision the evaluation supports (ship a prompt, switch a
   model, change retrieval) and pre-declare the gating metrics, floors and
   allowed regression before running anything.
2. Build or extend a versioned golden dataset with ids, provenance, tags for
   normal, adversarial, must-refuse and no-answer slices, and a held-out split
   ([datasets-and-metrics.md](references/datasets-and-metrics.md),
   [golden_dataset.jsonl.template](assets/golden_dataset.jsonl.template)).
3. Choose the cheapest metric per requirement: exact or fuzzy match, schema
   validity, task-specific code checks first; RAG answer metrics for
   grounded generation; retrieval metrics stay with `kit-retrieval`.
4. Add an LLM judge only with a versioned rubric, a pinned judge, bias
   controls and measured agreement with human labels
   ([judges-and-statistics.md](references/judges-and-statistics.md),
   [judge_rubric.md.template](assets/judge_rubric.md.template)).
5. Copy the stdlib [harness](assets/eval_harness.py.template); keep model
   calls behind the `kit-llm-client` port and use fakes in tests.
6. Plan finite sweeps of model alias, prompt version, temperature and seed
   with the `kit-config` experiment template and approve the total cost
   ([experiments.md](references/experiments.md)). For optional program
   optimization, use the [DSPy boundary](references/dspy.md) and
   [input-only adapter](assets/dspy_task.py.template); keep the final holdout
   outside optimization.
7. Record run identity on every run: run id, exact prompt version, model
   alias and served snapshot, dataset fingerprint, scorer versions.
8. Repeat cases when sampling is enabled; report means with bootstrap
   intervals and the minimum detectable difference; compare paired cases.
9. Gate in CI with absolute floors, baseline regression tolerances, safety
   slices, and cost and latency ceilings; update baselines only by decision.
10. Optionally mirror runs to Langfuse datasets and experiments through the
    [experiment adapter](assets/langfuse_experiment.py.template) after export
    approval.
11. Run red-team and safety slices; keep evaluation data private and reports
    content-free.
12. Record the outcome in the
    [report worksheet](assets/eval_report.md.template); the asset map,
    commands and limits are in [references/guide.md](references/guide.md).

## Acceptance gates

- Dataset version and content fingerprint appear on every report; ids are
  unique and every case has provenance.
- Gating metrics, thresholds and tolerances were declared before the run.
- Each judge used as a gate has a versioned rubric and recorded agreement
  with human labels above the declared minimum.
- Means carry confidence intervals; deltas below the minimum detectable
  difference are reported as no measurable change.
- Runs reference an exact prompt version, never only a label.
- CI fails on harness exit code 1; invalid input exits 2 and is not retried.
- Must-refuse and adversarial slices meet their gates; no production personal
  data entered datasets, traces or reports without approval.

## Failure modes

- A single sample per case presented as a stable result.
- Uncalibrated judges gating releases; position and length bias unmeasured.
- Baselines silently replaced by the latest passing run.
- Datasets edited in place so comparisons cross versions.
