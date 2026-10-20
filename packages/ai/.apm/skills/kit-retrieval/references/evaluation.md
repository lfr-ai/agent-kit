# Retrieval evaluation

Retrieval quality is measured, versioned, and gated in CI like any other
behavior. Generation quality depends on it, but evaluate retrieval separately
first: a generator cannot cite evidence it never received.

## Golden sets

A golden set is a versioned JSON Lines file of judged queries (format read by
`load_golden_set` in [retrieval_metrics.py.template](../assets/retrieval_metrics.py.template)):

```json
{"query_id": "q-001", "text": "how do I export invoices", "subject": "synthetic-staff", "gains": {"chunk-a": 2, "chunk-b": 1}}
{"query_id": "q-002", "text": "rocket engine maintenance", "subject": "synthetic-staff"}
```

- Use synthetic principals and synthetic or approved documents; never copy
  production queries or personal data into a repository.
- Include no-answer queries (no positive gains). Correct behavior for them is
  an empty result or `NO_EVIDENCE`.
- Include permission cases: the same query as two principals with different
  expected results, and a query whose only relevant chunk is invisible to the
  caller (expected: no evidence).
- Judge at source or chunk level consistently. Chunk ids change when chunking
  changes; source-level judgments survive re-chunking but measure less.
- Grade relevance (for example 2 = answers the question, 1 = related context)
  so nDCG can reward ordering.
- Grow the set from real failure reports after removing sensitive content;
  record why each item was added.

## Metrics

| Metric | Question it answers | Notes |
| --- | --- | --- |
| Recall@k | Did the evidence reach the generator? | Primary gate; use the `k` you send to the model |
| Precision@k | How much noise did we send? | Drives token cost and distraction |
| MRR | How early is the first relevant hit? | Sensitive to the head only |
| nDCG@k | Is the ordering good given graded relevance? | Best single ranking metric with graded judgments |
| No-evidence accuracy | Do unanswerable queries abstain? | Guards against confident fabrication |
| Citation precision | Do answer citations point at retrieved chunks? | Fabricated or leaked citations fail |
| Faithfulness or groundedness | Is every claim supported by retrieved text? | Needs a judge model or human review |
| Latency p50/p95, cost per query | Is it affordable at the target load? | Track beside quality |

All ranking metrics in the template are deterministic, raise on undefined
inputs (no relevant items, no positive gain) instead of returning a misleading
zero, and are unit tested.

## Groundedness and faithfulness

Faithfulness asks whether every claim in an answer is supported by the
retrieved context. Practical approaches, in increasing cost:

1. Citation checks: every sentence carries a citation, every citation points
   at a retrieved chunk (`citation_precision`), and the cited span exists
   (`text[start:end]` matches).
2. Lexical support heuristics: flag answer sentences with low overlap with
   their cited spans for review.
3. Model judges that split the answer into claims and verify each against the
   context. Pin the judge model and prompt version, calibrate the judge on a
   small human-labelled sample, and report judge agreement.

Never use the generating model as the only judge of its own answers.

## Running an evaluation

1. Build the index from a fixed corpus snapshot with a recorded chunker,
   normalizer, and embedding model version.
2. Run every golden query as its synthetic principal and record retrieved ids.
3. Call `evaluate(runs, golden, k=...)` and store the report with the
   configuration that produced it.
4. Compare against the previous baseline; fail CI when recall@k or
   no-evidence accuracy drops beyond an agreed tolerance.
5. Inspect `misses` before tuning anything.

## Pitfalls

- Tuning on the evaluation set: keep a held-out split for final comparisons.
- Averaging over too few queries: report the count; a 30-query set cannot
  distinguish a two-point change.
- Comparing runs across different corpus snapshots.
- Treating a judge model's score as ground truth.

## Sources

- [scikit-learn ndcg_score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html)
- [TREC evaluation measures (trec_eval)](https://github.com/usnistgov/trec_eval)
- [Ragas faithfulness metric](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)
- [OpenAI evaluation best practices](https://platform.openai.com/docs/guides/evaluation-best-practices)
