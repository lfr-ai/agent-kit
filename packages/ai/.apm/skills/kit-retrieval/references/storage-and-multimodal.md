# Select a retrieval backend without changing the contract

Use this guide when a plain lexical or vector baseline no longer meets a measured
requirement. Do not install every framework or add another always-on skill.
Keep the [adapter boundary](framework-adapters.md), access filtering, deletion
and evaluation contracts independent of the selected backend.

## Decision table

| Candidate | Choose when | Evidence required before adoption |
| --- | --- | --- |
| SQLite | Embedded metadata, test fixtures or a single-node application fit its write-concurrency limits | Transactions, busy handling, backup/restore and actual filesystem behavior; do not use a shared network file as a multi-writer service |
| PostgreSQL with pgvector | Relational metadata, tenancy and transactional lifecycle already live in PostgreSQL | Query plans, index recall, tenant filtering, deletion and migration tests using the delivered SQL/adapter assets |
| FAISS | Local vector search needs a benchmarked index with an explicit surrounding metadata store | Index/model dimension match, durable metadata and ACL mapping, atomic index replacement, restore and concurrent-access tests |
| Neo4j / Cypher | Relationship traversal improves answer quality over the baseline | Parameterized Cypher, bounded traversal, tenant/permission predicates on every traversed object, provenance for edges and evidence returned |
| LightRAG | A graph/vector pipeline removes concrete ingestion and retrieval work | Storage isolation, extraction/model versions, ACL and deletion behavior across every derived store; compare against the baseline rather than assuming graph retrieval is better |
| RAG-Anything | Images, tables, equations or mixed documents require multimodal ingestion | Parser/model compatibility, content size and time limits, source page/region attribution, sandboxed parsing, artifact access controls and multimodal evaluation |
| LangChain / LlamaIndex | Existing loaders, retrievers or orchestration demonstrably reduce adapter work | Pin the consumer's compatible versions; reuse the delivered adapter contract tests and preserve metadata/authorization at the boundary |
| Ollama or another local model endpoint | Residency, offline operation or cost requires local inference | Explicit server/model identity, memory/concurrency bounds, transport/auth review and measured quality; a local endpoint is not automatically trusted |

Upstream framework integrations can change between versions. LightRAG's upstream
documentation includes multimodal support with RAG-Anything; check the chosen
release before building two overlapping ingestion stacks.
Popularity is a maintenance signal, not proof of security or fit.

## Corrective and graph retrieval

The existing [corrective retriever](../assets/self_corrective_retriever.py.template)
provides bounded rounds, time budgets and repeat detection. Use it for a
self-corrective/CRAG-style experiment before adding a second orchestration engine.
Record the grader, rewrite policy, baseline, no-answer outcome and measured gain.
Do not treat a model's confidence as authorization or factual evidence.

Graph-derived entities, summaries and relationships inherit the source's access
constraints. Revoke them when the last supporting source is deleted. Joining a
public node to a private edge must not leak the private source through labels,
scores, snippets or generated summaries.

## Ingestion and serialization boundaries

- Treat documents, URLs, archive members and extracted metadata as untrusted.
  Bound redirects, archive expansion, file sizes, parser time and temporary files.
- Separate document parsing from code execution. Never evaluate document content,
  deserialize untrusted pickle data, or enable dangerous framework deserialization
  merely to load an unknown index.
- Store a manifest with source/version, extraction version, embedding model and
  dimensions. A model or schema change requires a new index and controlled swap.
- Keep database credentials and model tokens out of manifests and logs.
  Record identifiers, counts and timing, not confidential queries or documents.

## Adoption and verification

1. Fill the [backend acceptance record](../assets/backend-acceptance.md.template)
   with the use case, exact versions, baseline and removal plan.
2. Run the existing fake-adapter, chunking, fusion, deletion and metrics tests.
3. Add the same cases against the proposed backend: other tenant, revoked access,
   deleted/stale source, incomplete metadata, duplicate ingestion and unavailable
   backend. Assert filters run before evidence reaches a model.
4. Measure recall/no-answer accuracy and latency, memory, ingestion cost and
   per-query cost on the same versioned dataset. Define acceptable thresholds
   before comparing; do not invent a universal chunk size or result count.
5. Exercise restore, index replacement, cancellation and rollback with synthetic
   data. Require an explicit unsupported result when the backend cannot enforce a
   required contract; do not return an apparently successful empty result.

These are selection and verification procedures, not installed adapters or
certification of the named products. The consumer owns dependency audits,
services, integration tests and the measured decision.

## Primary sources

- [SQLite usage boundaries](https://www.sqlite.org/whentouse.html)
- [pgvector](https://github.com/pgvector/pgvector)
- [FAISS FAQ](https://github.com/facebookresearch/faiss/wiki/FAQ)
- [Neo4j GraphRAG Python](https://neo4j.com/docs/neo4j-graphrag-python/current/)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [RAG-Anything](https://github.com/HKUDS/RAG-Anything)
- [Ollama API](https://docs.ollama.com/api/introduction)
