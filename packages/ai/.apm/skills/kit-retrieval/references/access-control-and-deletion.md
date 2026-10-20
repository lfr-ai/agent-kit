# Access control and deletion propagation

A retrieval index is a copy of source data. It must enforce the same read
permissions as the source and forget what the source forgets. Both properties
fail silently, so they need explicit design and tests.

## Threat model

| Threat | Example | Control |
| --- | --- | --- |
| Cross-tenant disclosure | A shared index returns another customer's document | Tenant column on every row, filtered in the query; tenant-specific statistics |
| Over-broad read inside a tenant | A staff member retrieves a restricted document | Per-chunk access list matched against principal tokens before ranking |
| Disclosure through the model | Restricted text reaches the prompt, then the answer | Filter before reranking, grading and prompt assembly |
| Disclosure through side channels | Scores or result counts reveal hidden documents | Compute statistics over visible data; do not return counts of filtered rows |
| Stale permissions | A user removed from a group still retrieves its documents | Resolve groups at query time; reindex access lists on change |
| Zombie content | Deleted source still retrievable, or resurrected by a slow job | Delete plus tombstone in one transaction; ingestion checks tombstones |
| Prompt injection via indexed content | A document instructs the model to reveal other data | Treat retrieved text as untrusted data; keep authorization outside the model |

## Access model

The templates use a deliberately simple, deny-by-default model:

- Each chunk has a `tenant` and a non-empty `acl` of principal tokens such as
  `user:alice` and `group:finance`, copied from the source at ingestion.
- A `Principal` resolves to `user:<subject>` plus one `group:<id>` token per
  group membership, resolved from the identity provider at request time.
- `is_visible_to` requires the same tenant and at least one shared token.

Map richer source permissions (roles, folder inheritance, sharing links) into
tokens during ingestion. If the source model cannot be expressed as tokens,
query the source's permission API at retrieval time for the candidate set and
document the latency cost.

## Enforcement points

1. Ingestion: refuse sources without an access list; copy it to every chunk,
   graph node and summary derived from the source.
2. Query: filter by tenant, tokens and metadata inside the store, before
   ranking (`InMemoryIndex.candidates`, the SQL `WHERE` clauses in
   [pgvector_store.py.template](../assets/pgvector_store.py.template)).
3. Fusion and reranking: re-check visibility after fusion as defense in depth
   (`HybridRetriever`), and treat any dropped hit as a defect to alert on.
4. Prompt assembly: only `RetrievalResult.hits` reach the prompt; cached
   answers and conversation memory are scoped to the principal that produced them.
5. Answer: citations point at chunks the caller could read; citation
   precision below 1.0 is a failure.

Approximate vector indexes often filter after the index scan. Filtering then
returns fewer rows rather than more, which is safe for access but harmful for
recall; use iterative scans, partial indexes, or per-tenant partitions.

## Deletion propagation

Deletion must reach every derived copy: chunks, embeddings, lexical indexes,
graph nodes and summaries, caches of query results, evaluation snapshots, and
backups according to the retention policy.

- Delete by source in one transaction and record a tombstone (`delete_source`).
- Ingestion checks the tombstone under the same lock before writing, so an
  in-flight job that read the source before deletion cannot resurrect it
  (`SourceDeletedError`, and the advisory lock in the pgvector adapter).
- On edit, upsert the new version first, then `retain_version` to remove old
  chunks. Readers see either the old or the new version, never neither.
- Reconcile periodically: list source ids in the index and compare with the
  source of truth; delete orphans and alert on drift.
- Invalidate answer caches keyed by any deleted chunk or source.
- Removing a tombstone (for example a restored document) is an explicit
  operator action, never a side effect of ingestion.

## Permission changes

- Group membership changes take effect immediately because tokens are resolved
  per request.
- Source access-list changes require re-writing the `acl` of every chunk of the
  source. Treat an access-list change like a new version: upsert, then retain.
- Measure and alert on the delay between a source permission change and the
  index reflecting it.

## Tests that must exist

- Cross-tenant query returns nothing from the other tenant.
- Principal without a token gets nothing; group member gets the document.
- A faulty adapter that ignores filters is caught by the post-fusion check.
- Deleted source is not retrievable and cannot be re-upserted.
- Old versions are removed after `retain_version`.
- Golden-set permission cases pass (see [evaluation](evaluation.md)).

## Sources

- [OWASP Top 10 for LLM applications: vector and embedding weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/)
- [OWASP Top 10 for LLM applications: prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [PostgreSQL row security policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [PostgreSQL advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS)
- [pgvector filtering and iterative index scans](https://github.com/pgvector/pgvector#filtering)
