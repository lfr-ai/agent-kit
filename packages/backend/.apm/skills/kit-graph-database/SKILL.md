---
name: kit-graph-database
description: Use when modeling a Neo4j graph, writing Cypher, defining constraints or indexes, or building a graph repository.
license: MIT
---

# Store and query a property graph with Neo4j

## Procedure

1. Confirm a graph fits: write the multi-hop questions the application must
   answer, the server edition and version, and whether a relational store
   already serves them. Retrieval-augmented generation over a graph is owned by
   the `kit-retrieval` skill; this skill covers the database and its adapter.
2. Model nodes, relationships, and properties from those questions per
   [graph modeling](references/modeling.md): stable business keys, specific
   relationship types, intermediate nodes for n-ary facts, and no supernodes on
   hot paths.
3. Declare constraints and indexes before data or `MERGE` arrives, using the
   idempotent [schema template](assets/schema.cypher.template). Note which
   constraints need Enterprise Edition and enforce the rest in the adapter.
4. Write every query as a constant with `$parameters` in a
   [query catalog](assets/query_catalog.py.template), per
   [Cypher queries](references/cypher-queries.md): `MERGE` on keys only,
   `UNWIND` batches for writes, `LIMIT` or a keyed seek on every read, bounded
   variable-length paths, and allow-listed labels instead of formatted text.
5. Implement the port in a [graph repository](assets/graph_repository.py.template)
   per [driver and transactions](references/driver-transactions.md), against the
   [port and minimal domain types](assets/purchase_domain.py.template): one driver
   per process, sessions per unit of work, `execute_read`/`execute_write` with
   idempotent, side-effect-free transaction functions, explicit database, and
   translated driver errors.
6. Check plans with `EXPLAIN` and `PROFILE` on representative data; each entry
   point must start with an index seek. Treat APOC as an explicit, pinned
   dependency.
7. Adapt the [contract tests](assets/test_graph_repository.py.template) to run
   against a disposable Neo4j container with the schema applied: idempotent
   writes, constraint errors, bounded pages, and index-seek plans.
8. Run [check_cypher_queries.py](assets/check_cypher_queries.py) on the touched
   Python and Cypher files and resolve or explicitly waive every finding.
9. Review against the [graph guide](references/guide.md) security rules,
   anti-patterns, and limits.

## Acceptance gates

- No Cypher text is built with f-strings, concatenation, `%`, or `str.format`;
  labels and relationship types come from an allow-list.
- Every `MERGE` targets a property backed by a uniqueness or key constraint.
- Every read query is bounded by `LIMIT`, an aggregate, or a unique-key seek,
  and every variable-length pattern has an upper bound.
- Transaction functions are idempotent, perform no external side effects, and
  return plain values, never `Result` or `Record` objects.
- The schema script is idempotent and the contract tests pass on the production
  edition and major version.
- `check_cypher_queries.py` reports no unreviewed findings.

## Checker

```text
python check_cypher_queries.py src graph
python check_cypher_queries.py src --templates --exclude fixtures
```

Prints `path:line: rule: message`; exit 0 clean, 1 findings, 2 unusable input.
Waive a reviewed finding with `# cypher-safety: reviewed` in Python or
`// cypher-safety: reviewed` in Cypher. The checks are textual heuristics, not
a parser or a plan analysis.

## References

- [Graph database review guide](references/guide.md)
- [Graph modeling, constraints, and indexes](references/modeling.md)
- [Writing Cypher queries](references/cypher-queries.md)
- [Driver lifecycle and transactions](references/driver-transactions.md)
