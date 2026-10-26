# Graph data modeling, constraints, and indexes

Reviewed 2026-10-23 against the Neo4j Cypher Manual (Cypher 5 and Cypher 25
pages) and the Neo4j graph modeling guidelines. Edition and version notes are
marked; confirm them for the consumer's server before relying on them.

## Model from the questions

Write the traversals the application must answer first, then shape the graph so
each one starts from an indexed node and follows few, selective relationships.

| Concept | Model as | Example |
| --- | --- | --- |
| Thing with identity and its own lifecycle | Node with a label and a unique key property | `(:Customer {customerId})` |
| Fact connecting two things, possibly with attributes | Relationship with a specific type and direction | `(:Customer)-[:PLACED {at}]->(:Order)` |
| Scalar attribute read with its owner | Property | `name`, `createdAt` |
| Value shared and queried by many nodes (category, country) | Node, when traversed through; property, when only filtered | `(:Product)-[:IN_CATEGORY]->(:Category)` |
| Fact involving more than two things or carrying history | Intermediate node | `(:Employment {from, to})` between person and company |

Conventions: labels in `PascalCase`, relationship types in `UPPER_SNAKE_CASE`,
properties in `camelCase`. Use one specific relationship type per meaning
(`:SHIPPED_TO`, not `:RELATED {kind: "shipped"}`): the type is part of the index
the traversal uses. Store a stable business key instead of relying on internal
element identifiers, which the server may reuse after deletion.

## Supernodes

A supernode has so many relationships that every traversal through it reads
them all (a `:Country` linked to every customer, a `:Tag` on every document).

- Do not model low-cardinality attributes used only for filtering as nodes; use
  an indexed property instead.
- Split by time or partition (`:Day`, `:Bucket`) when fan-out grows without bound.
- Traverse into a dense node from the selective side and filter on relationship
  type and direction; never expand all relationships of a dense node.
- Watch the degree distribution (`COUNT { (n)--() }`) in tests with realistic data.

## Constraints

Create constraints before loading data or running `MERGE`; they also create the
index the lookup uses. Use `IF NOT EXISTS` and explicit names so schema scripts
are idempotent, as in the [schema template](../assets/schema.cypher.template).

| Constraint | Cypher | Edition |
| --- | --- | --- |
| Property uniqueness | `REQUIRE n.customerId IS UNIQUE` | All editions |
| Relationship property uniqueness | `FOR ()-[r:PAID_WITH]-() REQUIRE r.paymentId IS UNIQUE` | All editions, 5.7 and later |
| Property existence | `REQUIRE n.email IS NOT NULL` | Enterprise |
| Property type | `REQUIRE n.createdAt IS :: ZONED DATETIME` | Enterprise, 5.9 and later |
| Node or relationship key | `REQUIRE (n.tenantId, n.orderId) IS NODE KEY` | Enterprise |

Cypher 25 on Neo4j 2026.02 and later (Enterprise) adds graph types, which
declare node and relationship element types with their constraints in one
schema. Adopt them deliberately; the classic `CREATE CONSTRAINT` commands remain
valid and are added to the graph type automatically.

On Community Edition, enforce existence and types in the adapter: the domain
object is validated before it is written.

## Indexes

| Index | Use for | Notes |
| --- | --- | --- |
| Range (default `CREATE INDEX`) | Equality, ranges, prefix, `ORDER BY` on properties | Composite indexes need every property in the predicate |
| Text | `CONTAINS` and `ENDS WITH` on strings | Not for ranges |
| Point | Spatial distance and bounding box | |
| Full-text (`CREATE FULLTEXT INDEX`) | Tokenized search with Lucene analyzers | Queried through `db.index.fulltext.queryNodes` |
| Vector (`CREATE VECTOR INDEX`) | Similarity search over embeddings | Dimensions and similarity function fixed at creation; retrieval design belongs to the `kit-retrieval` skill |
| Token lookup | Label and relationship type scans | Created by default; do not drop |

Verify with `SHOW INDEXES` / `SHOW CONSTRAINTS` and confirm that `EXPLAIN`
shows an index seek, not `AllNodesScan` or `NodeByLabelScan`, for every
entry-point lookup.

## Primary sources

- [Cypher Manual: constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Cypher Manual: create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Cypher Manual: search-performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/overview/)
- [Cypher Manual: vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Cypher Manual: graph types](https://neo4j.com/docs/cypher-manual/current/schema/graph-types/)
- [Neo4j graph data modeling guidelines](https://neo4j.com/docs/getting-started/data-modeling/guide-data-modeling/)
- [Cypher Manual: naming rules and recommendations](https://neo4j.com/docs/cypher-manual/current/syntax/naming/)
