# LLM evaluation guide

## Purpose

Measure whether a model-backed feature is good enough, and whether a change
made it better or worse, with versioned data, calibrated scorers, honest
uncertainty and enforced gates. The `kit-llm-client` evaluation reference is
the short summary; this skill is the full procedure.

## References

| Topic | Reference |
| --- | --- |
| Golden datasets, offline and online modes, metric catalogue, RAG answer metrics, red-teaming, privacy | [datasets-and-metrics.md](datasets-and-metrics.md) |
| Judge rubrics, bias controls, calibration, variance, intervals, regression gates | [judges-and-statistics.md](judges-and-statistics.md) |
| Run identity, kit-config sweeps, Langfuse datasets and experiments, cost and latency | [experiments.md](experiments.md) |

Owners elsewhere, referenced by name: retrieval metrics in `kit-retrieval`;
prompt versions, labels and rollout in `kit-llm-client`; experiment planning
in `kit-config`; agent trajectories in `kit-agent-systems`.

## Assets and copy targets

| Asset | Copy to | Depends on |
| --- | --- | --- |
| [eval_harness.py.template](../assets/eval_harness.py.template) | `evals/harness.py` | stdlib |
| [langfuse_experiment.py.template](../assets/langfuse_experiment.py.template) | `evals/adapters/langfuse_experiment.py` | harness, consumer Langfuse SDK facade |
| [golden_dataset.jsonl.template](../assets/golden_dataset.jsonl.template) | `evals/datasets/<name>-v1.jsonl` | none |
| [judge_rubric.md.template](../assets/judge_rubric.md.template) | `evals/rubrics/<metric>-v1.md` | none |
| [eval_report.md.template](../assets/eval_report.md.template) | pull request or release record | harness report |
| [agents.json](../assets/agents.json) | native role source | toolkit renderer |

Score recorded outputs offline:

```text
python evals/harness.py evals/datasets/support-v1.jsonl \
  --outputs runs/run-example/job-000/outputs.jsonl --dataset-version support-v1 \
  --baseline evals/baselines/support-v1.json --min exact_match=0.8 \
  --max-regression 0.02 --report runs/run-example/job-000/report.json
```

## Verification

- Copy the harness and run its tests with fake tasks and recorded outputs:
  loading, duplicate and unknown-field rejection, scorer bounds, seeded
  bootstrap reproducibility, gate floors, baseline identity and regression,
  finite non-negative tolerances, and exit codes 0, 1 and 2.
- A complete harness JSON report can be reused unchanged as a baseline. It
  includes `dataset_fingerprint` and `scorer_versions` alongside the existing
  numeric `metrics` and per-metric `details`. A baseline may compare a subset
  of metrics; every compared metric must be known, finite, in `[0, 1]`, and
  have the same scorer version as the candidate.
- Legacy metrics-only baselines are intentionally rejected with exit 2, as
  are missing, malformed or mismatched provenance and empty/invalid metrics.
  After an explicit approval, re-score the baseline outputs with the current
  dataset and scorers and save the complete report. Do not guess provenance,
  relabel old metrics, or automatically replace a baseline on a passing run.
- Scorers expose an explicit implementation `version`; bump it whenever the
  scoring definition changes. Custom callers pass the actual scorer-version
  mapping to `build_report`, not a placeholder or the harness release version.
- With neither `--min` nor `--baseline`, the harness only scores: exit 0 and
  `passed: true` mean no configured gates failed, not release approval. No
  thresholds are invented; `--max-regression` must still be finite and
  non-negative.
- The Langfuse adapter is executed against an offline fake facade here:
  denied export makes zero facade, task or scorer calls; approved runs
  forward only allowlisted run metadata, preserve case source/tags, and pass
  a positive concurrency bound. Facade, task and scorer exceptions propagate
  without retry. The consumer facade must enforce the concurrency bound and
  surface item failures. Test it against the pinned SDK before hosted use.
- Offline aggregation and the Langfuse evaluator share the harness
  `validate_score` rule: only finite numeric values in `[0, 1]` are accepted,
  excluding booleans. Invalid scores raise `EvalInputError` before a score
  record or successful experiment summary is returned; they are not clamped
  or converted into passing scores.

## Limits

The harness does not call models, run judges, or certify statistical
validity of a consumer's design. Scores are only as meaningful as the dataset
and the calibrated scorers. No hosted service, judge model or CI system is
exercised by the toolkit tests.
