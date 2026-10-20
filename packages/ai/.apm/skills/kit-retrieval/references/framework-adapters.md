# Framework adapter boundaries

LangChain, LlamaIndex, vector database clients and embedding SDKs change
faster than retrieval requirements. Keep them at the edge of the application,
behind ports you own, so a framework upgrade or replacement touches one
adapter module and its contract tests.

## Layering

```text
retrieval.contracts       ports, value objects, errors (stdlib only)
retrieval.chunking        pure functions over contracts
retrieval.fusion          pure functions over contracts
retrieval.metrics         pure functions
retrieval.retrievers      framework-free strategies and test doubles
retrieval.self_corrective orchestration over ports
retrieval.settings        configuration (stdlib only)
retrieval.adapters.*      one module per framework or driver
composition root          builds adapters from settings and injects them
```

Dependencies point inward. [importlinter.ini.template](../assets/importlinter.ini.template)
enforces three contracts: the core imports no framework, driver or adapter;
contracts import nothing else from the package; adapters do not import each
other. Run `lint-imports` in CI beside the unit tests.

## What an adapter owns

- Translating `Query` into the framework call, including a per-principal,
  pre-filtered retriever (the factory pattern in
  [langchain_adapter.py.template](../assets/langchain_adapter.py.template)
  and [llamaindex_adapter.py.template](../assets/llamaindex_adapter.py.template)).
- Translating results into `ScoredChunk` with full provenance through
  `chunk_from_mapping`, which fails closed when metadata is missing.
- Mapping transport and timeout errors to `RetrievalUnavailableError`.
- Re-checking visibility of every result and logging any violation as a defect.

## What an adapter must not do

- Decide authorization. It applies the filter derived from the principal and
  verifies the result; the policy lives in `is_visible_to` and the ingestion
  pipeline.
- Leak framework types (`Document`, `NodeWithScore`, driver rows) past its
  module boundary.
- Retry silently. Retries belong to a bounded policy at the call site so the
  time budget stays visible.
- Change ranking semantics without a recorded evaluation.

## Contract tests

Write one parametrized test module that runs the same cases against the
in-memory retrievers and every real adapter (against the local vector store
from [compose.vector-store.yaml.template](../assets/compose.vector-store.yaml.template)):

1. Visible matches are returned in rank order with provenance.
2. Another tenant's chunks are never returned.
3. A principal without a matching token gets nothing.
4. Metadata filters apply inside the store.
5. Deleted sources disappear and cannot be re-upserted.
6. Old versions disappear after `retain_version`.
7. Backend failure maps to `RetrievalUnavailableError`.

[test_retriever_adapters.py.template](../assets/test_retriever_adapters.py.template)
encodes cases 1 to 6 against the reference implementation; mark the real
adapter variant as an integration test that needs the container.

## Choosing a framework at all

Use a framework adapter when it removes real work (loaders for many formats,
a managed index type you need, an evaluation harness). Skip it when the
application needs only one store and plain SQL or a client library does the
job; the pgvector adapter in [pgvector_store.py.template](../assets/pgvector_store.py.template)
is about 300 lines with no framework.

## Upgrades

- Pin framework versions; upgrade one adapter at a time behind its contract tests.
- Read the release notes for changes to default `k`, score semantics, filter
  syntax and async behavior; these change results without failing tests that
  only check types.
- Re-run the golden-set evaluation after any adapter upgrade.

## Sources

- [import-linter contract types](https://import-linter.readthedocs.io/en/stable/contract_types/)
- [LangChain retrievers](https://docs.langchain.com/oss/python/integrations/retrievers)
- [LangChain BaseRetriever reference](https://reference.langchain.com/python/langchain-core/retrievers/BaseRetriever)
- [LlamaIndex retrievers](https://developers.llamaindex.ai/python/framework/module_guides/querying/retriever/)
- [LlamaIndex metadata filters](https://developers.llamaindex.ai/python/framework/module_guides/indexing/vector_store_index/)
- [Psycopg 3 connection pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
