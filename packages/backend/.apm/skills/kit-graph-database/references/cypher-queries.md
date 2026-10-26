# Writing Cypher queries

Reviewed 2026-10-23 against the Neo4j Cypher Manual and the Neo4j Python
Driver Manual (driver 6, current).

## Parameters, always

Values reach the server as parameters (`$name`). The query text stays constant,
so the server caches its plan and user input can never change its structure.

```python
# Good: constant text, values as parameters.
FIND_CUSTOMER = "MATCH (c:Customer {customerId: $customer_id}) RETURN c"
records, _, _ = await driver.execute_query(FIND_CUSTOMER, customer_id=customer_id)

# Bad: user input becomes Cypher.
await driver.execute_query(f"MATCH (c:Customer {{name: '{name}'}}) RETURN c")
```

The Python driver annotates query text as `typing.LiteralString`
([PEP 675](https://peps.python.org/pep-0675/)), so a type checker rejects
formatted strings at the call site; keep that check enabled.

Labels, relationship types, and property keys cannot be ordinary parameters.
When the structure must vary:

1. Map the input to a closed allow-list (`StrEnum`) and select one of several
   constant queries, or
2. On Neo4j 5.26 and later, use dynamic labels with a parameter,
   `MATCH (n:$($label))` or `MERGE ()-[r:$($rel_type)]->()`, still validated
   against the allow-list. Check the plan: some server versions cannot use
   property indexes with dynamic labels.

Never build labels with string concatenation, and never pass user text to
procedures that execute Cypher strings (`apoc.cypher.run` and similar).

## MERGE semantics

`MERGE` matches the whole pattern or creates the whole pattern.

| Pitfall | Effect | Instead |
| --- | --- | --- |
| `MERGE (c:Customer {customerId: $id, name: $name})` | A changed name creates a duplicate customer | `MERGE` on the key only, then `ON CREATE SET` / `SET` other properties |
| `MERGE (a:A {id: $a})-[:R]->(b:B {id: $b})` | Creates new `a` and `b` nodes when the relationship is missing | `MERGE` each node by key, then `MERGE (a)-[:R]->(b)` |
| `MERGE` without a uniqueness constraint under concurrency | Two transactions can create the same node | Create the constraint first; it makes `MERGE` lock and seek |
| `MERGE` on a property that can be null | Fails with a null property error | Validate keys before the write |

```cypher
MERGE (c:Customer {customerId: $customer_id})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name, c.updatedAt = datetime()
```

## Batching with UNWIND

Send many rows as one list parameter and one query per batch, not one query per
row:

```cypher
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name, p.price = row.price
```

Choose a batch size (for example 1000 to 10 000 rows) that keeps one transaction
within memory and timeout limits; measure it. For very large loads use
`CALL { ... } IN TRANSACTIONS OF n ROWS` in an auto-commit query (with
`session.run`, not a managed transaction) or the offline import tool.

## Bounded reads and pagination

- Every read that can return many rows ends with `LIMIT`. Aggregations
  (`count`, `sum`) and lookups by a unique key are naturally bounded.
- Bound variable-length paths: `-[:REPORTS_TO*1..5]->`, never `*` alone.
- Paginate with `ORDER BY` on a unique, indexed property and a keyset predicate
  (`WHERE o.createdAt > $after ... ORDER BY o.createdAt LIMIT $page_size`);
  `SKIP` grows linearly with depth like SQL `OFFSET`.
- Return only the properties the caller needs (`RETURN o {.orderId, .status}`)
  instead of whole nodes with large properties.

## Plans

- `EXPLAIN` shows the plan without running the query; `PROFILE` runs it and
  reports rows and database hits per operator. Profile against representative
  data, never against production writes.
- Look for `NodeIndexSeek` at the entry point; `AllNodesScan`, `NodeByLabelScan`
  on a large label, `CartesianProduct`, or `Eager` on a write are review items.
- Rewrite disconnected patterns that produce a Cartesian product into one
  connected pattern or separate `MATCH` clauses joined by `WITH`.

## APOC and procedures

APOC Core ships with some distributions; APOC Extended is a separate plugin and
is often unavailable in managed services. Prefer built-in Cypher (subqueries,
`COLLECT`, `CALL ... IN TRANSACTIONS`, dynamic labels) when it covers the need,
pin the plugin version when it does not, and keep procedure use inside the
adapter so the dependency is visible. Allow-list procedures on the server.

## Primary sources

- [Cypher Manual: parameters](https://neo4j.com/docs/cypher-manual/current/syntax/parameters/)
- [Cypher Manual: MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Cypher Manual: UNWIND](https://neo4j.com/docs/cypher-manual/current/clauses/unwind/)
- [Cypher Manual: CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Cypher Manual: query tuning and plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)
- [Neo4j Knowledge Base: protecting against Cypher injection](https://neo4j.com/developer/kb/protecting-against-cypher-injection/)
- [Python Driver Manual: query the database](https://neo4j.com/docs/python-manual/current/query-simple/)
- [APOC documentation](https://neo4j.com/docs/apoc/current/)
