# Retrieval strategies

Pick the cheapest strategy that meets a measured recall target on your golden
set (see [evaluation](evaluation.md)). Every strategy below plugs into the
`Retriever` port in [retrieval_contracts.py.template](../assets/retrieval_contracts.py.template),
so strategies can be swapped or fused without touching answer assembly.

## Decision table

| Need | Start with | Add when measured | Watch out for |
| --- | --- | --- | --- |
| Exact identifiers, codes, error strings, names | Lexical (BM25 or full-text) | Dense for paraphrases | Tokenizer and stemming choices change recall |
| Paraphrased natural-language questions | Dense embeddings | Lexical via hybrid fusion | Embedding model drift; re-embed on model change |
| Mixed workloads (most products) | Hybrid: lexical + dense fused with RRF | Reranker on the fused head | Over-fetch enough candidates before fusion |
| Precision of the top three matters most | Hybrid + cross-encoder reranker | Query rewriting | Reranker latency and cost per candidate |
| Vague or multi-intent questions | Query rewriting or decomposition | Self-corrective loop | Rewrites must never widen permissions |
| Answers spread across linked entities | Graph or entity-linked retrieval | Community summaries | Graph build cost and staleness |
| Low-confidence answers are harmful | Any strategy + relevance grading + abstention | Human escalation | Explicit `NO_EVIDENCE` handling downstream |

## Lexical retrieval (BM25)

BM25 scores a chunk by summing, for each query term, an inverse document
frequency weight multiplied by a saturating term-frequency factor that is
normalized by chunk length. Two parameters matter:

- `k1` (typically 1.2 to 2.0) controls how quickly repeated terms stop adding score.
- `b` (typically 0.75) controls how strongly long chunks are penalized; set it
  lower when chunk lengths are uniform by construction.

Strengths: exact matches, rare tokens, product codes, and no model to host.
Weaknesses: vocabulary mismatch ("bill" versus "invoice") and language-specific
analysis. PostgreSQL `ts_rank_cd` is a cover-density ranking, not BM25; the
[pgvector_store.py.template](../assets/pgvector_store.py.template) lexical
strategy uses it and must be evaluated on its own merits. Compute corpus
statistics over the principal's visible candidates or over the whole tenant,
never across tenants: cross-tenant document frequencies leak the existence of
hidden content through score shifts.

## Dense retrieval

Embed chunks and queries with the same model and compare vectors with cosine
similarity or inner product. Rules that prevent most production defects:

- Record the embedding model identifier and dimensions with the index; refuse
  to query an index built by a different model (the `PgIndexWriter` checks
  dimensions at construction).
- Approximate indexes (HNSW, IVF) trade recall for latency. Filtering is often
  applied after the index scan, which silently returns fewer rows; pgvector
  0.8 and later can scan iteratively (`hnsw.iterative_scan`) to compensate.
- Normalize text the same way at indexing and query time.
- Similarity is a ranking signal, not a probability of correctness. Do not use
  a raw cosine threshold as an "answer is true" gate.

## Hybrid retrieval and reciprocal rank fusion

Run lexical and dense strategies concurrently, over-fetch each (for example
four times `top_k`), then fuse. Reciprocal rank fusion scores each chunk as the
sum over rankings of `weight / (k + rank)`, with `k` around 60. Because RRF uses
ranks only, it needs no score calibration across strategies, which is exactly
what makes BM25 scores and cosine similarities combinable.

Implementation notes ([rrf_fusion.py.template](../assets/rrf_fusion.py.template)):

- Deduplicate within a ranking before fusing; a chunk counts once per strategy.
- Break ties deterministically (best original rank, then id) so tests and
  evaluations are reproducible.
- Weights are a tuning knob of last resort; prefer fixing the weaker strategy.
- Alternatives such as convex score combination need per-strategy score
  normalization and more tuning; RRF is the robust default.

## Reranking

A cross-encoder or model-based reranker reads the query and each candidate
together and is far more precise than bi-encoder similarity, at a much higher
per-candidate cost. Rerank only the fused head (for example 20 to 50
candidates), keep `top_n` small, and set a latency budget. The reranker sees
chunk text, so it is inside the data boundary: apply access filtering before
reranking, never after.

## Query rewriting

Rewriting turns a conversational or underspecified question into one or more
retrieval queries: expanding acronyms, resolving pronouns from conversation
history, decomposing multi-part questions, or generating a hypothetical answer
passage to embed (HyDE). Constraints:

- A rewrite changes text only. Principal, tenant, filters and `top_k` are
  copied from the original query (`Query.with_text` enforces this).
- Bound the number of rewrites and detect repeats (the self-corrective loop
  stops on an empty or repeated rewrite).
- Log rewrite counts and outcomes, not the rewritten text, unless the logging
  policy explicitly allows query content.

## Self-corrective and corrective retrieval

Corrective patterns add a judge between retrieval and generation:

1. Retrieve.
2. Grade whether the hits can support an answer (`SUFFICIENT`,
   `INSUFFICIENT`, `NO_EVIDENCE`).
3. If insufficient, rewrite the query using the grader's reason and retry.
4. Stop at a round limit or time budget, then abstain explicitly.

[self_corrective_retriever.py.template](../assets/self_corrective_retriever.py.template)
implements this loop with a bounded number of rounds, a wall-clock budget,
repeat detection, and an opt-in policy for returning partial evidence. Some
published variants also fall back to web search when local evidence is weak;
treat any external fallback as a new data source with its own trust, privacy
and citation rules, and never enable it implicitly.

Graders can be cheap (term coverage, as in `KeywordOverlapGrader`), a
cross-encoder score threshold calibrated on the golden set, or a model judge.
Model judges must return a typed grade; parse failures count as
`INSUFFICIENT`, not as success.

## Graph retrieval

Graph-oriented retrieval extracts entities and relations during ingestion and
answers questions by traversing neighborhoods or by retrieving precomputed
community summaries. It helps when evidence is spread across many documents
connected by shared entities (for example "which suppliers are affected by
this part recall"). Costs and risks:

- Extraction uses a model per chunk; budget it and make it idempotent per
  source version.
- Every node and edge needs the same provenance and access list as the chunks
  it was derived from. A summary that merges content from sources with
  different access lists must carry the intersection of their access lists, or
  must not be produced.
- Deleting a source must delete or recompute the nodes, edges and summaries
  derived from it.

Treat graph retrieval as another `Retriever` and fuse it with RRF; do not let it
bypass the port.

## Failure modes

- Fusion over strategies that were each truncated to `top_k` loses most of the
  benefit; over-fetch before fusing.
- Silently degrading to one strategy when the other fails hides recall
  regressions; `HybridRetriever` fails the request instead.
- Post-filtering an approximate index returns fewer than `top_k` results
  without any error.
- Re-embedding with a new model into the same index mixes incomparable vectors.

## Sources

- [Okapi BM25 in Apache Lucene](https://lucene.apache.org/core/9_12_0/core/org/apache/lucene/search/similarities/BM25Similarity.html)
- [PostgreSQL full text search](https://www.postgresql.org/docs/current/textsearch.html)
- [pgvector documentation](https://github.com/pgvector/pgvector)
- [Reciprocal rank fusion (Cormack, Clarke, Buettcher, SIGIR 2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [Elasticsearch reciprocal rank fusion](https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html)
- [OpenSearch hybrid search](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/)
- [Sentence Transformers cross-encoder usage](https://sbert.net/docs/cross_encoder/usage/usage.html)
- [Corrective retrieval augmented generation (arXiv 2401.15884)](https://arxiv.org/abs/2401.15884)
- [Self-RAG (arXiv 2310.11511)](https://arxiv.org/abs/2310.11511)
- [Hypothetical document embeddings (arXiv 2212.10496)](https://arxiv.org/abs/2212.10496)
- [Microsoft GraphRAG documentation](https://microsoft.github.io/graphrag/)
