# Repositories as ports

A repository gives the domain the illusion of an in-memory collection of
aggregates. In Hexagonal Architecture it is a driven (secondary) port: the core
declares the interface, and infrastructure provides adapters.

## Declare the port in the core

```python
class OrderRepository(Protocol):
    def get(self, order_id: OrderId, /) -> Order | None: ...
    def add(self, order: Order, /) -> None: ...
    def save(self, order: Order, /) -> None: ...
```

Rules:

- One repository per aggregate root.
- Speak the domain language: `get`, `add`, `save`, `find_open_for_customer`; not
  `execute`, `query`, or SQL fragments.
- Accept and return domain objects, never ORM rows, documents, or dictionaries.
- Keep query methods few and purposeful. Reporting and search queries belong to
  a separate read model, not the aggregate repository.
- Concurrency: `save` raises a domain-level `ConcurrencyError` when the stored
  version differs from the version the aggregate was loaded with.
- Missing aggregates: return `None` from `get` and let the application service
  decide whether that is an error, or provide a `require` helper that raises a
  documented `NotFoundError`.

## Adapters

- Production adapter in infrastructure (`SqlOrderRepository`) maps rows to
  aggregates using the aggregate's restore factory, and aggregates to rows.
- In-memory adapter for tests (`InMemoryOrderRepository`) stores copies, honors
  the same version checks, and lives with the test support code or in
  infrastructure when local tooling uses it.
- Both adapters run the same contract test suite so the fake cannot drift from
  production behavior.

## Transactions

The application service owns the transaction boundary, usually through a unit
of work port: begin, call repositories, commit, publish collected events. A
repository method does not commit on its own.

## Binding check

[check_port_adapter_binding.py](../assets/check_port_adapter_binding.py) reports
every `Protocol` port in a core package that has no adapter class implementing
all of its methods in the adapter packages:

```text
python check_port_adapter_binding.py --core src/shop/core --adapters src/shop/infrastructure
python check_port_adapter_binding.py --core src/shop/core \
    --adapters src/shop/infrastructure --adapters tests/fakes --ignore "^Clock$"
```

Matching is structural (method names and invocation kind), so adapters need
not inherit from the Protocol. Base classes defined in the scanned adapter files
contribute their methods.

A coroutine must match a coroutine; an async generator is not a coroutine.
A normal `def` port annotated with bare or qualified `AsyncIterator`, optionally
subscripted, can be bound to an async-generator adapter method. Ordinary
functions and synchronous generators remain compatible as before. Incompatible
invocation kinds remain unbound and retain the `async mismatch` diagnostic when
reported as a closest adapter's missing member.

This is an AST-only shape check, not type equivalence or runtime verification.
Yield detection skips nested function, class and lambda definitions, including
their headers. Annotation imports, aliases, strings, shadowing and element types
are not resolved; other return types and callable-transforming decorators need
a type checker. An `async def` returning `AsyncIterator` without its own yield
is still a coroutine and cannot satisfy the synchronous iterator-factory port.

## Anti-patterns

- Generic repositories (`Repository[T]` with `filter(**kwargs)`) that leak query
  semantics into the domain.
- Returning lazy ORM objects that load more data outside the transaction.
- Repositories that publish events or send emails.
- Domain code that imports the concrete adapter.

## Templates

[repository_port.py.template](../assets/repository_port.py.template),
[in_memory_repository.py.template](../assets/in_memory_repository.py.template),
and [test_in_memory_repository.py.template](../assets/test_in_memory_repository.py.template),
which doubles as a contract suite for the production adapter.

## Sources

- [Martin Fowler: Repository](https://martinfowler.com/eaaCatalog/repository.html)
- [Martin Fowler: Unit of Work](https://martinfowler.com/eaaCatalog/unitOfWork.html)
- [Alistair Cockburn: Hexagonal architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [PEP 544 - Protocols](https://peps.python.org/pep-0544/)
- [Microsoft: Design the infrastructure persistence layer](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/infrastructure-persistence-layer-design)
