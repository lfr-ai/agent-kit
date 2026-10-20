---
description: Apply to persistence adapters, SQL, schemas, and database migrations.
applyTo: "**/*repository*.py,**/*model*.py,**/alembic/**,**/migrations/**,**/*.sql"
---

- Keep database sessions and ORM types at persistence boundaries, not in domain policy; return domain objects or DTOs.
- Bind values as parameters; never interpolate untrusted values into SQL, and allow-list dynamic table or column names.
- Make transaction ownership explicit: one unit of work per use case, committed or rolled back by its owner, not inside a repository helper.
- Avoid N+1 access: load related rows deliberately with joins or batched queries, and select only the needed columns.
- Paginate list queries with a stable order; prefer keyset pagination for large or changing tables.
- Back every uniqueness and referential rule with a database constraint, not only application checks.
- Set statement and lock timeouts; keep transactions short and free of calls to other services.
- Review locks, query count, indexes, data volume, and mixed-version rollout for schema changes.
- Use expand-and-contract migrations: add nullable or defaulted columns, backfill in batches, switch readers, then remove the old shape in a later release.
- Keep migrations ordered and reversible only when rollback semantics are real; never edit an applied migration, add a new one.
- Test persistence constraints and migration upgrades against the supported database engine, not a substitute.
- Use the `kit-database-migrations` skill for migration authoring and review.
