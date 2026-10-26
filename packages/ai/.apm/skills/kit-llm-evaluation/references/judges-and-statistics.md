# Judges, variance and statistical gates

Reviewed 2026-10-23.

## LLM-as-judge

A model judge is a measuring instrument. Pin and version it like code.

1. Write a rubric with one question, a binary or short ordinal scale, anchor
   examples and automatic-fail conditions
   ([rubric template](../assets/judge_rubric.md.template)).
2. Pin the judge model alias, record the served snapshot, set temperature to
   the lowest supported value, and validate the verdict against a schema.
3. Give the judge only what the rubric needs. Hide candidate identity, model
   name and run label.
4. Prefer several narrow binary judges to one broad 1-10 score; narrow
   questions are easier to calibrate and to explain.
5. Count judge errors (invalid JSON, refusals, timeouts) separately; never
   score them as pass or fail.

### Known biases and controls

| Bias | Symptom | Control |
| --- | --- | --- |
| Position | Pairwise judge prefers the first or second answer | Run both orders; disagreement is a tie |
| Verbosity | Longer answers score higher | Length is not a criterion; include length-matched controls |
| Self-preference | Judge favors outputs from its own model family | Use a different family where possible; check with human labels |
| Leniency drift | Scores creep up after judge model updates | Pin snapshot; re-calibrate on any judge change |
| Reference anchoring | Judge copies the reference instead of assessing support | Ask about support or contradiction, not similarity |

### Calibration against human labels

- Sample cases stratified by tag; have at least two people label a subset
  with written instructions and measure their agreement (Cohen's kappa).
  If humans disagree, fix the rubric before calibrating the judge.
- Measure judge versus consensus human labels on a held-out sample: kappa,
  true and false positive rates. Decide the minimum agreement before looking.
- Re-calibrate after any change to judge model, judge prompt or rubric, and
  on a schedule with sampled audits of production scores.
- A judge that fails calibration may still be used for exploration, never as
  a release gate.

## Variance and repeated runs

Model outputs vary between calls even at temperature zero, and seeds are
best-effort. Treat one run as one sample.

- Run each case several times (three to five is a common start) whenever
  sampling is enabled, and whenever a decision depends on small differences.
- Average within a case first, then aggregate across cases; the case is the
  independent unit, not the individual call. The
  [harness](../assets/eval_harness.py.template) does this and reports
  `repeat_spread` as the mean per-case range.
- Record the served model snapshot or system fingerprint; a provider-side
  change explains many unexplained shifts.

## Confidence intervals and detectable differences

- Report every mean with a bootstrap confidence interval over cases. The
  harness uses a seeded percentile bootstrap so reports are reproducible.
- For baseline versus candidate on the same cases, analyze per-case paired
  differences (paired bootstrap or a paired test). Paired designs detect
  smaller changes than comparing two independent means.
- Before trusting a delta, compare it with the minimum detectable
  difference. The harness estimate uses a two-sample normal approximation at
  95 % confidence and 80 % power; it is a planning number, not a test.
- Too few cases is the most common reason for false conclusions. With 50
  binary cases and a mean near 0.8, the interval is roughly plus or minus 0.1.
- Multiple metrics and slices inflate false alarms. Pre-declare the gating
  metrics; treat the rest as diagnostics.

## Regression gates in CI

| Gate | Form | Example |
| --- | --- | --- |
| Absolute floor | Mean not below a fixed value | `schema_validity >= 0.99` |
| Baseline regression | Mean not below baseline minus tolerance | `exact_match >= baseline - 0.02` |
| Safety slice | Zero tolerance on a slice | No must-refuse case answered |
| Cost and latency | Ceiling or relative increase | p95 latency within 10 % of baseline |

- Store the baseline report (metrics, dataset fingerprint, prompt version,
  model snapshot) in version control or an artifact store; update it only by
  an approved decision, never automatically on a passing run.
- A harness baseline requires a non-empty numeric `metrics` object, the same
  `dataset_fingerprint`, and matching `scorer_versions` for every compared
  metric. Each scorer's explicit implementation revision identifies its
  scoring definition, not just its name; bump it when that definition changes.
  Unknown metrics, non-finite means, values outside `[0, 1]`, or invalid
  provenance exit 2 before comparison. Regression tolerance must be finite
  and non-negative, even in scoring-only runs.
- A complete harness report roundtrips directly as a baseline; `metrics` and
  `details` retain their existing shapes. Metrics-only legacy baselines are
  intentionally invalid. After approval, regenerate them by re-scoring the
  baseline outputs with the current dataset and scorers. When either identity
  changes, re-run the baseline first; never stamp new provenance onto old means.
- Run deterministic scorers on every pull request with recorded or fake
  outputs; run real-model evaluations on prompt, model or parameter changes
  with a total cost budget, and nightly for drift.
- Exit codes of the harness (0 pass, 1 gate failure, 2 invalid input) map
  directly to CI job status. Never retry an evaluation job until it passes.
- Without floors or a baseline the harness is scoring-only: exit 0 and
  `passed: true` mean no configured gate failed, not that a release is approved.
  The template does not choose release thresholds for the consumer.

## Primary sources

- [Langfuse LLM-as-a-judge](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [Zheng et al., Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)
- [Anthropic: a statistical approach to model evaluations](https://www.anthropic.com/research/statistical-approach-to-model-evals)
- [Efron and Tibshirani, An Introduction to the Bootstrap (publisher page)](https://www.routledge.com/An-Introduction-to-the-Bootstrap/Efron-Tibshirani/p/book/9780412042317)
- [Python statistics module](https://docs.python.org/3/library/statistics.html)
