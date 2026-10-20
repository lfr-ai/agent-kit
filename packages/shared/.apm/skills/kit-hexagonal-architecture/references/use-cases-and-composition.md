# Use cases, application services and the composition root

## What a use case owns

A use case (application service) is one user-meaningful operation:
"settle an invoice", "register a user", "export a document". It owns:

1. **Orchestration** - load what is needed through driven ports, ask the domain
   to decide, persist the decision, trigger follow-up effects.
2. **The transaction boundary** - it opens the unit of work and decides when to
   commit. Repositories never commit on their own.
3. **The order of side effects** - which effects happen before commit, which
   after, and what happens if one of them fails.
4. **Input and output shapes** - a command object in, a result object out, both
   independent of HTTP, CLI or message formats.

It does **not** own business rules that belong to a single entity (those go in
the domain), wire formats (driving adapters), or retries, timeouts and
connection pools (driven adapters or the composition root).

See [`use_case.py.template`](../assets/use_case.py.template) for a complete
example and [`test_use_case.py.template`](../assets/test_use_case.py.template)
for its tests.

## Shape

- One class per use case with a single public `__call__` (or `execute`), or a
  plain function taking its collaborators as keyword arguments. Both are fine;
  pick one style per codebase.
- Collaborators arrive through keyword-only constructor parameters typed by
  ports. No service locators, no module-level singletons, no `import` of an
  adapter.
- Commands and results are frozen, keyword-only dataclasses. Validate syntax
  (types, required fields) in the driving adapter; validate business rules in
  the domain.
- Return a result object instead of printing or building a response.
- Raise domain or port exceptions; let the driving adapter translate them to
  status codes or exit codes.

## Idempotency and repeat calls

Driving adapters retry (HTTP clients, message redelivery, impatient users).
Design use cases so a repeat call is safe:

- Detect "already done" from persisted state and return the earlier outcome
  (`already_paid=True`).
- Derive idempotency keys for external effects from stable identifiers
  (`settle-{invoice_id}`), not from timestamps or random values.
- Order effects so a crash between two steps leaves a state a retry can finish.

## When to split or merge

Split a use case when two callers need different transaction boundaries or
different failure policies. Merge two use cases when one always calls the
other with no extra decisions. Avoid a generic `InvoiceService` with twenty
methods; it becomes a dumping ground with no clear transaction ownership.

## The composition root

Exactly one place constructs adapters and use cases
([`composition.py.template`](../assets/composition.py.template)):

1. Read and validate configuration once, reporting every missing value at once.
2. Construct driven adapters with explicit timeouts, pools and credentials.
3. Inject them into use cases.
4. Hand use cases to driving adapters (CLI parser, HTTP routes, worker loop).

Rules that keep it honest:

- Only the composition root (and tests) import from `adapters/`.
- Lifetimes are explicit: a connection factory per unit of work, a client per
  process, a token provider that refreshes. Do not hide lifetimes inside
  module globals.
- Prefer plain constructor calls over a dependency-injection container. A
  container is worth it only when wiring itself becomes the hard problem, and
  even then keep it inside the composition root.
- Frameworks with their own dependency mechanisms (request-scoped providers,
  app factories) are driving adapters; resolve use cases there from the
  composition root rather than letting framework objects travel inward.

## Testing the wiring

A class name matching an expected adapter is not proof of wiring. Add one
composition test that builds the real graph with safe settings (temporary
database file, a transport that refuses network) and runs one use case end to
end. It catches missing arguments, wrong lifetimes and circular imports that
unit tests with fakes cannot see.

## Sources

- Alistair Cockburn, [Hexagonal architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- Robert C. Martin, [The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- Python documentation, [dataclasses](https://docs.python.org/3/library/dataclasses.html)
- Microsoft, [Common web application architectures](https://learn.microsoft.com/en-us/dotnet/architecture/modern-web-apps-azure/common-web-application-architectures)
