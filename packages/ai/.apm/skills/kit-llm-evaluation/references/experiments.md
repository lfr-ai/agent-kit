# Experiments, sweeps and tracking

Reviewed 2026-10-23. Langfuse is optional; every step works with the stdlib
harness and local files.

## Run identity

Every experiment run records enough to reproduce and compare it:

| Field | Source |
| --- | --- |
| Run id, job index, seed, temperature | `kit-config` experiment planner |
| Prompt name and exact numeric version | Managed prompt resolution (`kit-llm-client` prompt management) |
| Model alias and served snapshot or fingerprint | Completion metadata from the client port |
| Dataset version and content fingerprint | Harness `dataset_fingerprint` |
| Scorer, judge and rubric versions | Evaluation code and rubric file |
| Code revision and dependency lock digest | CI environment |

Evaluate exact prompt versions, never a mutable label such as `production`.
A label is resolved to a version at run time; record the version. Promotion of
a label after a passing run follows the rollout procedure in the
`kit-llm-client` prompt-management reference.

## Sweeps with the kit-config experiment template

Use the `kit-config` skill's reproducible-experiments reference and its
`experiment_config.py.template` and `experiment.json.template` to plan sweeps.
Hydra is optional and only composes configuration for ChatGPT/OpenAI API
parameter and evaluation experiments; it is not a training or inference-serving
platform here. Other providers need the same explicit compatibility review.

1. Fix the dataset version and fingerprint before planning; a sweep compares
   settings, never datasets.
2. Choose explicit finite axes: model alias, prompt version, temperature and
   seed. Each job is a billed run over the whole dataset; multiply job count by
   cases and repeats to get the candidate call count. Add optimizer, judge,
   retry and validation calls before approving the total cost. A job-count cap
   alone is not a spending limit.
3. Plan jobs with `parse_experiment` and `plan_runs`, write each manifest, then
   run the candidate once per job and record outputs as JSONL beside the
   manifest.
4. Score each job with the [harness](../assets/eval_harness.py.template) and
   keep the reports with the manifests.
5. Compare jobs pairwise on the same cases; seeds measure variance, they are
   not separate candidates. Report the spread across seeds.
6. Select a candidate only on the pre-declared gating metrics, then confirm it
   on the held-out split once.

## Langfuse datasets, experiments and scores

| Concept | Use | Rule |
| --- | --- | --- |
| Dataset | Hosted copy of approved cases | Upload only approved data; record the dataset version timestamp |
| Experiment (dataset run) | One candidate run over a dataset | Name it with the kit-config `run_id`; attach run metadata |
| Score | Numeric, categorical or boolean result on a trace or run | Same names and definitions as the offline harness |
| Online evaluator | Judge or code check on sampled live traces | Calibrated before alerting; sampled, not exhaustive |

- Copy the [experiment adapter](../assets/langfuse_experiment.py.template)
  to run harness scorers through a consumer-owned SDK facade. It refuses to
  run unless export is explicitly approved, attaches allow-listed metadata
  (run id, dataset version and fingerprint, prompt name and version, model
  alias, temperature, seed) and reuses the offline scorers so hosted and local
  scores mean the same thing.
- Fetch datasets at a pinned version when comparing runs over time; the
  latest version can change underneath a comparison.
- The SDK experiment runner sets its own concurrency and tracing; configure
  concurrency, timeouts and flushing in the facade, within the run budget.
- Keep the local harness report as the gate of record; hosted dashboards
  are for inspection and comparison.

## Cost and latency

- Record tokens, cost and latency per call through the client port, then
  aggregate per case and per run: p50 and p95 latency, mean and total cost.
- Gate cost and latency like quality. A cheaper candidate that fails a
  quality gate is rejected; a better one that doubles p95 latency needs an
  explicit decision.
- Include judge calls in the run cost; judges often dominate it.

## Failure modes

- Comparing runs on different dataset versions or scorer versions.
- Evaluating through a mutable prompt label and recording the label only.
- Treating seeds as independent candidates and picking the luckiest one.
- Uploading production traces to a hosted dataset without approval.
- Unbounded sweeps: ranges, globs or adaptive searches without a cost ceiling.

## Primary sources

- [Langfuse evaluation concepts](https://langfuse.com/docs/evaluation/core-concepts)
- [Langfuse experiments via SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk)
- [Langfuse experiments in CI/CD](https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd)
- [Langfuse datasets](https://langfuse.com/docs/evaluation/experiments/datasets)
- [Langfuse prompt version control](https://langfuse.com/docs/prompt-management/features/prompt-version-control)
- [Hydra multirun](https://hydra.cc/docs/tutorials/basic/running_your_app/multi-run/)
