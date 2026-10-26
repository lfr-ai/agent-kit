# Typed ORM mapping and repository adapters

Reviewed 2026-10-23 against the SQLAlchemy 2.0 documentation. The 2.x series
keeps these APIs; confirm the consumer's pinned minor version before copying.

## Declarative typed models

Use the 2.0 annotated declarative style so a type checker sees column types:

```python
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class OrderRow(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(STATUS_LENGTH))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

| Rule | Why |
| --- | --- |
| `Mapped[X]` is non-nullable; `Mapped[X \| None]` is nullable | Nullability follows the annotation, so the type and the schema agree |
| Give strings an explicit length and store timestamps aware (`DateTime(timezone=True)` or a UTC type decorator) | Avoids engine-specific defaults and naive datetimes |
| Set a `naming_convention` on `MetaData` | Constraint names become deterministic, which migrations need to drop or alter them |
| Store money as `Numeric(precision, scale)` mapped to `Decimal` | Binary floats lose cents |
| Store enums by value in a string column with a check constraint | Renaming a Python member must not rewrite data; native enum types are harder to migrate |
| Declare relationships with `lazy="raise"` | Accidental lazy loads fail in tests instead of issuing hidden queries; async sessions cannot lazy load at all |
| Define the referenced class first and avoid bidirectional relationships unless both directions are queried | Keeps annotations unquoted and the mapping small |
| Use `version_id_col` for rows updated concurrently | The ORM adds `WHERE version = :old` and raises `StaleDataError` on a lost update |

Schema changes to these models ship through migrations owned by the
`kit-database-migrations` skill.

## Rows never leave the adapter

ORM rows are persistence types. A repository adapter implements a domain port
(declared per the `kit-domain-model` skill; layer mapping rules live in the
`kit-hexagonal-architecture` skill) and returns domain objects:

| Direction | Function | Rule |
| --- | --- | --- |
| Row to domain | `_to_domain(row)` | Construct the domain type through its validating constructor so corrupt rows fail loudly |
| Domain to new row | `_new_row(entity)` | Map every field explicitly; no `**vars(entity)` |
| Domain to existing row | `_apply(entity, row)` | Copy changed fields onto the tracked row so the unit of work emits one `UPDATE` |

Anti-patterns:

- Returning `OrderRow` from a port method, or declaring the domain entity as the
  ORM class. Lazy attributes, session state, and column renames then leak into
  business rules and tests.
- A generic `Repository[T]` with `get_by(**filters)`. It exposes query shape to
  callers; name the queries the domain needs instead.
- Repositories that call `commit()`. The unit of work owns the transaction; see
  [sessions and transactions](sessions-transactions.md).
- Mapping libraries or reflection for a handful of fields; explicit functions are
  easier to review and type-check.

## Translating driver errors

Catch SQLAlchemy exceptions in the adapter and raise the port's documented
error, chaining the cause:

| SQLAlchemy exception | Typical port error |
| --- | --- |
| `IntegrityError` on a unique constraint | `DuplicateOrderError` |
| `StaleDataError` (version mismatch) | `ConcurrentUpdateError` |
| `None` from `scalar_one_or_none()` | `OrderNotFoundError` |
| `OperationalError`, or `DBAPIError` with `connection_invalidated` | `StorageUnavailableError` (retryable) |

Map an `IntegrityError` to a duplicate only when it is a uniqueness violation
(PostgreSQL drivers report the constraint name; SQLite reports
`UNIQUE constraint failed` with the columns) and re-raise anything else, so a
foreign-key or check failure is not reported as a duplicate. Store and return
timestamps through a UTC type decorator: SQLite drops time zones on read. The
[models template](../assets/models_base.py.template) shows both the decorator
and the naming convention.

## Primary sources

- [ORM quick start](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
- [Declarative tables with mapped_column](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html)
- [Configuring constraint naming conventions](https://docs.sqlalchemy.org/en/20/core/constraints.html#configuring-constraint-naming-conventions)
- [Configuring a version counter](https://docs.sqlalchemy.org/en/20/orm/versioning.html)
- [Relationship loading techniques](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html)
- [Augmenting existing types with TypeDecorator](https://docs.sqlalchemy.org/en/20/core/custom_types.html#augmenting-existing-types)
- [Martin Fowler, Repository](https://martinfowler.com/eaaCatalog/repository.html)
