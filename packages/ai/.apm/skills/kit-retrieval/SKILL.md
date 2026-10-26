---
name: kit-retrieval
description: Use when designing retrieval pipelines that preserve source provenance, access controls, and useful failure behavior.
license: MIT
---

# Keep retrieval attributable and permission-aware

## Procedure

1. Identify authoritative sources, owners, freshness expectations, tenancy, and
   access rules. Record which identity provider resolves group membership.
2. Separate ingestion, normalization, chunking, embedding, indexing, retrieval,
   and answer assembly. Copy the ports and value objects from
   [retrieval_contracts.py.template](assets/retrieval_contracts.py.template)
   before choosing any framework.
3. Keep frameworks and drivers in `retrieval.adapters`; enforce it with
   [importlinter.ini.template](assets/importlinter.ini.template). Read
   [framework-adapters.md](references/framework-adapters.md) and
   [storage and multimodal selection](references/storage-and-multimodal.md)
   before adopting graph, multimodal or local-model integrations.
4. Chunk normalized, versioned sources with exact offsets, deterministic ids,
   section paths, and the source access list
   ([chunking.md](references/chunking.md),
   [chunking.py.template](assets/chunking.py.template)).
5. Choose the cheapest strategy that meets the recall target: lexical, dense,
   or hybrid with reciprocal rank fusion, then reranking or query rewriting
   only when measured ([retrieval-strategies.md](references/retrieval-strategies.md),
   [rrf_fusion.py.template](assets/rrf_fusion.py.template),
   [retriever_adapters.py.template](assets/retriever_adapters.py.template)).
6. Apply tenant, access-list, and metadata filters inside the store before
   ranking, reranking, grading, or prompt assembly; re-check after fusion
   ([access-control-and-deletion.md](references/access-control-and-deletion.md)).
7. Propagate deletions with tombstones and version retention so stale or
   deleted content cannot be retrieved or resurrected.
8. Bound corrective loops by rounds, wall-clock time, and repeat detection;
   return an explicit `NO_EVIDENCE` result when support is weak
   ([self_corrective_retriever.py.template](assets/self_corrective_retriever.py.template)).
9. Cite retrieved source locations and distinguish source facts from
   generated synthesis; never cite chunks that were not retrieved.
10. Treat retrieved text as untrusted data; authorization never depends on
    model output.
11. Load configuration once at startup and fail fast on invalid values
    ([retrieval_settings.py.template](assets/retrieval_settings.py.template)).
12. Stand up the local vector store for integration tests with
    [compose.vector-store.yaml.template](assets/compose.vector-store.yaml.template),
    [schema.sql.template](assets/schema.sql.template), and the adapter in
    [pgvector_store.py.template](assets/pgvector_store.py.template).
13. Evaluate with a versioned golden set that includes no-answer and
    permission cases ([evaluation.md](references/evaluation.md),
    [retrieval_metrics.py.template](assets/retrieval_metrics.py.template)).
14. Copy the matching tests and run them for every adapter; the asset map is in
    [references/guide.md](references/guide.md).

## Acceptance gates

- Every chunk carries `source_id`, `source_version`, `tenant`, a non-empty
  `acl`, timezone-aware `updated_at`, section path, and offsets where
  `text == source[start:end]`.
- Filtering happens in the store before ranking; a test proves another tenant
  and an unauthorized principal receive nothing.
- A deleted source is not retrievable and cannot be re-upserted; old versions
  are removed after a successful upsert.
- Retrieval returns `SUFFICIENT`, `INSUFFICIENT`, or `NO_EVIDENCE`, and answer
  assembly handles each explicitly.
- Corrective loops have a round limit, time budget, and repeat detection.
- Core modules import no framework or driver (`lint-imports` passes).
- Recall@k and no-evidence accuracy are measured on a golden set and gated
  against a recorded baseline.
- Copied template tests pass: chunking, fusion, metrics, retrievers and
  deletion, self-corrective loop, settings.

## Failure modes

- Similarity scores presented as proof of truth, completeness, or authorization.
- Approximate-index post-filtering silently returning fewer than `top_k` hits.
- Fusion over strategies truncated to `top_k` instead of over-fetched.
- Re-embedding with a different model into an existing index.
- Query text, chunks, or rewrites logged in violation of the retention policy.

## Assets

- [chunk_template.json.template](assets/chunk_template.json.template) — chunk manifest matching the `Chunk` contract.
- [references/guide.md](references/guide.md) — full asset map, copy targets, and test list.
