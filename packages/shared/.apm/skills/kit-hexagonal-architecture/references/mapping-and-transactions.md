# Mapping between layers and transaction boundaries

## Map at every boundary, in one direction each

Each layer has its own representation of the same concept. Translate at the
boundary and never let an outer representation travel inward.

| Boundary | From | To | Where the mapping lives |
| --- | --- | --- | --- |
| Driving adapter in | JSON body, CLI args, message payload | command object | the driving adapter |
| Use case to domain | command fields | entity/value objects | the use case or a domain factory |
| Domain to storage | entity | row, document, ORM model | the repository adapter (`_to_row`) |
| Storage to domain | row, document | validated entity | the repository adapter (`_from_row`) |
| Domain to provider | entity fields | wire request | the client adapter |
| Provider to port | wire response | port value object | the client adapter (`_receipt`) |
| Use case out | result object | response body, exit code | the driving adapter |

Rules for mapping code:

- **Validate when entering the domain.** Constructing the entity from a row
  runs its invariants (`Invoice.__post_init__`), so corrupt stored data fails
  loudly at the adapter instead of deep inside a rule.
- **Keep exact types exact.** Store money as decimal text or integer minor
  units, never binary floats. Store timestamps with an explicit offset and
  convert to aware `datetime` on read.
- **Map enums by value**, not by ordinal or by Python name, so renaming a
  member does not corrupt stored data.
- **Unknown or missing wire fields** raise the port's protocol error; do not
  default them silently.
- **One mapper per direction per adapter.** Hand-written functions are usually
  clearer than a generic mapping library for a handful of fields.

Avoid a "shared model" used by API, domain and database alike. It feels like
less code until a column rename becomes a breaking API change.

## The unit of work is the transaction boundary

A unit of work groups repository changes into one atomic commit
([`invoice_repository_port.py.template`](../assets/invoice_repository_port.py.template)):

- The use case opens it with `with`, calls `commit()` explicitly, and leaving
  the block without commit rolls back. Forgetting to commit is then a test
  failure, not a silent partial write.
- Repositories obtained from a unit of work share its connection or session
  and never commit themselves.
- The adapter decides *how*: one SQLite connection with `autocommit=False`
  ([`invoice_repository_adapter.py.template`](../assets/invoice_repository_adapter.py.template)),
  a database session, a document-store transaction.
- Keep units of work short: no user interaction, no sleeping, no unbounded
  loops inside one.

You do not need a unit-of-work abstraction when each use case makes a single
write that the store already makes atomic. Add one when a use case changes more
than one aggregate or row and partial success would be wrong.

## External effects and transactions do not compose

A database transaction cannot roll back an e-mail or a card charge. Decide per
effect:

| Effect | Typical placement | Making failures safe |
| --- | --- | --- |
| Charge or other non-repeatable remote write | inside the unit of work, before commit | idempotency key derived from a stable id; retry returns the same result |
| Notification, cache invalidation, webhook | after commit | failure is logged and retried separately; it never undoes the commit |
| Must-not-be-lost follow-up | write an outbox row in the same transaction | a separate worker delivers it at least once |

The [`use_case.py.template`](../assets/use_case.py.template) charges inside the
unit of work with a deterministic key, commits, then notifies. If the commit
fails after a successful charge, the next attempt reuses the key and the
provider returns the earlier receipt instead of charging twice.

## Concurrency

Two requests settling the same invoice concurrently can both read "open".
Choose a strategy explicitly and test it:

- optimistic: a version column checked in the `UPDATE ... WHERE version = ?`;
  zero updated rows means someone else won, so reload and decide;
- pessimistic: `SELECT ... FOR UPDATE` (where supported) inside the unit of work;
- idempotent effects: the remote side deduplicates by key, so a lost race costs
  nothing but a redundant call.

## Sources

- Python documentation, [sqlite3 transaction control](https://docs.python.org/3/library/sqlite3.html#transaction-control)
- [PEP 249: Python Database API Specification v2.0](https://peps.python.org/pep-0249/)
- Python documentation, [decimal](https://docs.python.org/3/library/decimal.html)
  and [datetime aware objects](https://docs.python.org/3/library/datetime.html#aware-and-naive-objects)
- Python language reference, [The with statement](https://docs.python.org/3/reference/compound_stmts.html#the-with-statement)
