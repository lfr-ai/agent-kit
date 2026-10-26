---
description: Apply to Cypher files and Python graph adapters using the Neo4j driver.
applyTo: "**/*.cypher,**/graph/**/*.py"
---

- Pass every value as a `$parameter`; keep query text constant and never format labels, types, or values into it.
- Select labels and relationship types from an allow-listed enum, never from caller input.
- `MERGE` only on properties backed by a uniqueness or key constraint, and set other properties with `ON CREATE SET` or `SET`.
- End every read with `LIMIT`, an aggregate, or a unique-key lookup, and give variable-length patterns an upper bound.
- Write in batches with `UNWIND $rows`, not one query per row.
- Keep transaction functions idempotent and free of external side effects; consume results inside them.
- Create schema with named `IF NOT EXISTS` constraints and indexes.
- Use the `kit-graph-database` skill for modeling, queries, and driver code.
