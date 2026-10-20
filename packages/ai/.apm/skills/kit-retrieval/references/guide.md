# Retrieval pipeline guide

## Purpose

Design retrieval pipelines that retain provenance, honor permissions, surface
verifiable evidence, and abstain when evidence is weak. This guide maps the
references and copyable assets of the skill.

## References

| Topic | Reference |
| --- | --- |
| BM25, dense, hybrid, RRF, reranking, rewriting, corrective loops, graph retrieval | [retrieval-strategies.md](retrieval-strategies.md) |
| Boundaries, sizing, normalization, chunk failure modes | [chunking.md](chunking.md) |
| Golden sets, recall@k, MRR, nDCG, groundedness | [evaluation.md](evaluation.md) |
| Keeping LangChain, LlamaIndex and drivers behind ports | [framework-adapters.md](framework-adapters.md) |
| Tenancy, access lists, deletion and permission propagation | [access-control-and-deletion.md](access-control-and-deletion.md) |

## Assets and copy targets

The Python templates form one consistent package named `retrieval`; rename
the package consistently if needed. Tests use only `pytest` and `asyncio.run`.

| Template | Copy to | Depends on |
| --- | --- | --- |
| [retrieval_contracts.py.template](../assets/retrieval_contracts.py.template) | `retrieval/contracts.py` | stdlib |
| [chunking.py.template](../assets/chunking.py.template) | `retrieval/chunking.py` | contracts |
| [rrf_fusion.py.template](../assets/rrf_fusion.py.template) | `retrieval/fusion.py` | contracts |
| [retrieval_metrics.py.template](../assets/retrieval_metrics.py.template) | `retrieval/metrics.py` | stdlib |
| [retriever_adapters.py.template](../assets/retriever_adapters.py.template) | `retrieval/retrievers.py` | contracts, fusion |
| [self_corrective_retriever.py.template](../assets/self_corrective_retriever.py.template) | `retrieval/self_corrective.py` | contracts, retrievers |
| [retrieval_settings.py.template](../assets/retrieval_settings.py.template) | `retrieval/settings.py` | chunking, self_corrective |
| [pgvector_store.py.template](../assets/pgvector_store.py.template) | `retrieval/adapters/pgvector.py` | psycopg, psycopg-pool, pgvector |
| [langchain_adapter.py.template](../assets/langchain_adapter.py.template) | `retrieval/adapters/langchain.py` | langchain-core |
| [llamaindex_adapter.py.template](../assets/llamaindex_adapter.py.template) | `retrieval/adapters/llamaindex.py` | llama-index-core |
| [importlinter.ini.template](../assets/importlinter.ini.template) | `.importlinter` | import-linter |
| [schema.sql.template](../assets/schema.sql.template) | `schema.sql` | PostgreSQL with pgvector |
| [compose.vector-store.yaml.template](../assets/compose.vector-store.yaml.template) | `compose.vector-store.yaml` | Docker Compose |
| [chunk_template.json.template](../assets/chunk_template.json.template) | test fixture | none |

Tests: [chunking](../assets/test_chunking.py.template),
[fusion](../assets/test_rrf_fusion.py.template),
[metrics](../assets/test_retrieval_metrics.py.template),
[retrievers and deletion](../assets/test_retriever_adapters.py.template),
[self-corrective loop](../assets/test_self_corrective_retriever.py.template),
[settings](../assets/test_retrieval_settings.py.template).

## Acceptance gates

- Each chunk stores `source_id`, `source_version`, `tenant`, `acl`,
  `updated_at`, section path, and exact character offsets.
- Tenant and access filters run inside the store before ranking; fused results
  are re-checked and violations are logged as defects.
- Deletions tombstone the source; ingestion cannot resurrect it.
- A defined `NO_EVIDENCE` result is returned when support is weak, and answer
  assembly honors it.
- A versioned golden set with no-answer and permission cases gates recall@k
  and no-evidence accuracy in CI.
- `lint-imports` keeps frameworks and drivers in `retrieval.adapters`.

## Failure modes

- Stale or deleted documents still returned by the index.
- Missing source identifiers preventing attribution.
- Indexing sensitive content without protection, or filtering only after
  content reached a model.
- Approximate-index post-filtering silently returning fewer results.

## Negative cases to test

Empty index, access denial, other tenant, malformed metadata, deleted source,
stale version, backend outage, repeated rewrite, exhausted time budget.

## Scope and limits

These assets are reference implementations and tests. They do not certify a
specific vector database, embedding model, or framework version, and they are
not a privacy or compliance review. Run the integration variant of the
contract tests against the real store before relying on an adapter.

## Sources

- [pgvector documentation](https://github.com/pgvector/pgvector)
- [LangChain retrieval concepts](https://docs.langchain.com/oss/python/langchain/retrieval)
- [LlamaIndex retrievers](https://developers.llamaindex.ai/python/framework/module_guides/querying/retriever/)
