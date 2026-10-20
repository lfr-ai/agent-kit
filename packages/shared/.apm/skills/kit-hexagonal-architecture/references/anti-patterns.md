# Hexagonal anti-patterns and their repairs

Each entry names the smell, how to detect it, and the smallest repair.

## Leaky port

**Smell:** the port mentions the technology: `execute_sql(query)`,
`post(url, json)`, parameters of SDK types, return values that are HTTP
responses or ORM rows.
**Detect:** grep port modules for imports of drivers, SDKs or HTTP libraries;
ask whether a second implementation (in-memory, another vendor) could satisfy
the port without emulating the first technology.
**Repair:** rename the operation after the business intent, introduce a small
port-owned value object, move translation into the adapter.

## Adapter leaking inward

**Smell:** the use case catches `sqlite3.IntegrityError` or reads
`response.status_code`.
**Detect:** an import contract that forbids the library in the core; Ruff
`banned-api` for standard-library modules.
**Repair:** translate in the adapter and raise the port's exception with the
cause chained.

## Pass-through port

**Smell:** a Protocol with one implementation, no fake, no contract test, and
methods that forward every argument unchanged.
**Detect:** [`check_ports_adapters.py`](../assets/check_ports_adapters.py)
lists one implementation; nothing in tests substitutes it.
**Repair:** delete the Protocol and call the module directly, or justify it by
adding the fake and contract test it was meant to enable.

## Interface per class

**Smell:** every service gets an `IThing` Protocol, including use cases and pure
domain helpers.
**Repair:** keep Protocols for driven collaborators that do I/O or need
substitution; let use cases and pure functions be concrete.

## Anaemic use case, fat adapter

**Smell:** business decisions (status checks, limits, rounding) live in the
HTTP handler or the repository query.
**Detect:** the same rule appears in two driving adapters; a rule cannot be
tested without a database.
**Repair:** move the decision into the domain entity or use case; keep the
query a plain fetch.

## God service

**Smell:** `InvoiceService` with many unrelated methods and constructor
parameters for every port in the system.
**Repair:** one use case per operation; share code through domain objects, not
through a service class.

## Repository that commits

**Smell:** `repository.save()` calls `commit()`; two saves in one use case can
half-succeed.
**Repair:** move commit to a unit of work owned by the use case; make the
contract test assert that exit without commit discards changes.

## Hidden composition

**Smell:** adapters constructed at import time (`client = HttpClient()` at
module scope), environment variables read inside adapters or use cases, or a
global registry looked up by string.
**Repair:** construct in the composition root, read configuration once, pass
values and objects explicitly.

## Shared model across layers

**Smell:** one class is the API schema, the domain entity and the ORM model.
**Repair:** split at the boundary that changes most often first (usually the
API); add mapping functions with round-trip tests.

## Mock-heavy application tests

**Smell:** tests assert `repo.save.assert_called_once_with(...)` and break on
every refactor while missing real bugs (forgotten commit, wrong order of
effects).
**Repair:** use fakes with state and assert on outcomes; keep the fakes honest
with contract tests ([`fake_adapters.py.template`](../assets/fake_adapters.py.template)).

## Layer folders without layer rules

**Smell:** `domain/`, `application/` and `infrastructure/` folders exist but an
import contract does not, and `domain` imports `infrastructure` somewhere.
**Repair:** add [`importlinter.ini.template`](../assets/importlinter.ini.template),
prove it fails on a deliberate bad import, then fix the existing violations or
record them as explicit, dated `ignore_imports` entries.

## Sources

- Alistair Cockburn, [Hexagonal architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- Import Linter, [contract types](https://import-linter.readthedocs.io/en/stable/)
- Python documentation, [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- Ruff, [banned-api (TID251)](https://docs.astral.sh/ruff/rules/banned-api/)
