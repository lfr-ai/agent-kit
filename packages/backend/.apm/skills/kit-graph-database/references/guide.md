# Graph database review guide

Reviewed 2026-10-23. Topic detail lives in the sibling references linked from
[SKILL.md](../SKILL.md). Retrieval-augmented generation over a graph (GraphRAG,
vector plus traversal ranking, provenance of evidence) is owned by the
`kit-retrieval` skill; this guide covers the database adapter beneath it.

## Decision table

| Question | Default | Deviate when |
| --- | --- | --- |
| Graph or relational store? | Relational for records and reports | Questions are multi-hop traversals or path queries whose depth varies |
| Query API | `execute_query` for one statement | Several statements or client logic must be atomic: managed transaction |
| Write idempotency | `MERGE` on a constrained key | Append-only events: `CREATE` with a unique event id constraint |
| Bulk load | `UNWIND` batches in managed transactions | Initial load of millions of rows: offline import tool |
| Dynamic labels | Constant queries selected by an allow-listed enum | Many labels on Neo4j 5.26+: `$(...)` dynamic labels validated by the allow-list |

## Review checklist

| Area | Question | Reference |
| --- | --- | --- |
| Model | Does every entry-point lookup hit a constrained or indexed property? | [modeling](modeling.md) |
| Supernodes | Are high-degree nodes avoided or entered from the selective side? | [modeling](modeling.md) |
| Schema | Are constraints and indexes created idempotently before data loads? | [modeling](modeling.md) |
| Parameters | Is every query a constant string with `$` parameters? | [Cypher queries](cypher-queries.md) |
| MERGE | Does each `MERGE` use only key properties of one element? | [Cypher queries](cypher-queries.md) |
| Bounds | Does every read end with `LIMIT`, aggregate, or seek a unique key, and are variable-length paths bounded? | [Cypher queries](cypher-queries.md) |
| Transactions | Are transaction functions idempotent, free of side effects, and consuming results? | [driver and transactions](driver-transactions.md) |
| Lifecycle | Is the driver created once and closed at shutdown, with sessions per unit of work? | [driver and transactions](driver-transactions.md) |

## Security

- Parameterize every value; allow-list labels, relationship types, property
  keys, and sort fields through a `StrEnum` before they shape a query.
- Never pass user text into procedures that execute Cypher strings or load
  URLs (`apoc.cypher.run`, `LOAD CSV FROM $url` with untrusted input).
- Connect with a least-privilege database user per service; restrict write and
  procedure privileges with role-based access control (Enterprise) or separate
  databases.
- Use `neo4j+s://` (or `bolt+s://`) with certificate verification outside local
  development; never disable verification in shared configuration.
- Tenant and permission predicates belong on every traversed node in
  multi-tenant graphs; a traversal through a shared node must not leak another
  tenant's data.
- Do not log query parameters or returned properties that may hold personal data.

## Testing

- Unit-test domain logic with an in-memory fake implementing the same port.
- Run the adapter contract tests against a disposable Neo4j in a container
  (Testcontainers `Neo4jContainer`), pinned by image digest and edition, with
  the [schema script](../assets/schema.cypher.template) applied first; see the
  [test template](../assets/test_graph_repository.py.template).
- Assert idempotency (running a write twice leaves one node), constraint errors,
  bounded reads, and `EXPLAIN` plans that start with an index seek.
- Skip locally when Docker is unavailable; CI must run the tier.

## Anti-patterns

- f-strings, `%`, `.format`, or `+` building Cypher text.
- `MATCH (n) RETURN n` or unbounded `*` paths in application code.
- One transaction per row in a loop instead of `UNWIND` batches.
- Returning `neo4j.Record`, `Node`, or `Result` objects from the adapter.
- Calling HTTP services or publishing events inside a transaction function.
- Relying on internal element ids as business identifiers.

## Verification

1. `python assets/check_cypher_queries.py src` reports no findings, or each
   remaining one carries `# cypher-safety: reviewed` (Python) or
   `// cypher-safety: reviewed` (Cypher) with a reason.
2. The schema script runs twice without error.
3. The contract tests pass on the server edition and major version used in
   production.
4. Entry-point queries show an index seek under `EXPLAIN`.

## Limits

The checker is static: it cannot see queries assembled in other modules, prove
a key lookup is unique, or measure plans. Profiling with production-like data
volume remains a manual step.

## Primary sources

- [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/)
- [Neo4j Python Driver Manual](https://neo4j.com/docs/python-manual/current/)
- [Neo4j Operations Manual: authentication and authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Knowledge Base: protecting against Cypher injection](https://neo4j.com/developer/kb/protecting-against-cypher-injection/)
- [Testcontainers for Python: Neo4j module](https://testcontainers-python.readthedocs.io/en/latest/modules/neo4j/README.html)
