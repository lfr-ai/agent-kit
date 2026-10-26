---
description: Apply to SQLAlchemy repository and persistence adapter modules.
applyTo: "**/repositories/**/*.py,**/persistence/**/*.py"
---

- Declare ORM models with `DeclarativeBase`, `Mapped[...]`, and `mapped_column`; nullability follows the annotation.
- Return domain objects from repository methods; ORM rows, sessions, and `Result` objects stay inside the adapter.
- Open every `Session` or `AsyncSession` with `with`/`async with`; never store one in a module global or share it across tasks.
- Repositories flush but never commit; the unit of work commits once per use case.
- Build SQL with the expression language or `text()` plus bound parameters; never format SQL text.
- Declare relationships `lazy="raise"` and load them explicitly with `selectinload` or `joinedload`.
- With async engines, use async drivers and session factories with `expire_on_commit=False`.
- Translate SQLAlchemy exceptions into the port's documented errors and chain the cause.
- Use the `kit-sql-persistence` skill for repository, session, and query work.
