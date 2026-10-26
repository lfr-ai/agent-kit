---
description: Apply to LLM evaluation datasets, scorers, judges, experiment configs, and evaluation reports.
applyTo: "**/evals/**,**/evaluation/**"
---

- Datasets are versioned and append-only by case id; a changed case gets a new id, and every case records its provenance.
- Use synthetic, expert-written or redacted cases; never copy production traces or personal data into a dataset without approval.
- Pin judge models, judge prompts and rubric versions; a judge gates releases only after measured agreement with human labels.
- Record run identity with every result: dataset version and fingerprint, exact prompt version (not a label), model alias and served snapshot, scorer versions.
- Report means with confidence intervals over cases and repeat cases when sampling is enabled; do not claim a difference smaller than the minimum detectable difference.
- Declare gating metrics, floors and regression tolerances before running; update baselines only by an explicit decision.
- Keep evaluation reports content-free (metrics, ids, digests), and keep evaluation tests offline with fakes or recorded outputs.
- Use the `kit-llm-evaluation` skill for datasets, judges, statistics, sweeps and gates.
