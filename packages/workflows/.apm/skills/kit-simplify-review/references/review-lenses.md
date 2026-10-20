# Review lenses

Each lens has signals to look for, a question that decides the finding, the
evidence to attach, and the usual replacement. Apply every lens to the scope;
most code passes most lenses, and a clean result is a valid outcome.

## 1. YAGNI: built for a future that has not arrived

Signals:

- Configuration keys, parameters or flags that have exactly one value in every
  caller and every environment.
- Extension points ("strategy", "provider", "plugin") with one implementation
  and no dated plan for a second.
- Versioned formats or migrations for data that has never been written in an
  older shape.
- Generic types where every use binds the same concrete type.

Deciding question: if this flexibility were removed today and needed in six
months, would adding it then cost meaningfully more than carrying it until
then? Usually not: a later change knows the real requirement.

Evidence: the number of distinct values or implementations in use (search the
repository and the deployment configuration), plus the absence of a tracked
requirement.

Replacement: hard-code the single value, inline the single implementation,
drop the type parameter. If an owner has a dated need, keep it and record a
debt marker that names the need.

## 2. Native first: reinventing what the platform provides

Signals:

- Hand-written parsing of formats the standard library already parses (JSON,
  CSV, dates, URLs, paths, command-line arguments, configuration files).
- Custom retry, caching, pooling, scheduling or concurrency primitives when the
  language or framework in use already ships one.
- Utility modules that wrap a single library call with a different name.
- A new dependency that covers a feature available in the runtime version the
  project already requires.

Deciding question: does the native facility meet the actual requirement,
including error behavior and edge cases the custom code handles on purpose?

Evidence: the native API name with its documentation link, and a short
comparison of behavior on the custom code's tested edge cases.

Replacement: see the [native-first catalogue](native-first.md). Delete the
wrapper; call the native API directly at the call sites.

## 3. Speculative abstraction

Signals:

- An interface or abstract base class with one implementation, defined in the
  same package as its only caller.
- Factories that build one type; registries with one entry; dependency
  injection containers wiring objects that never vary.
- Layers that only forward calls (a service calling a manager calling a
  repository with identical signatures).
- "Base" classes whose subclasses override everything.

Deciding question: does the abstraction hide a decision that changes
independently, or a boundary that tests must substitute? A test double for an
external system is a legitimate reason; "we might swap it" is not.

Evidence: implementation count, the forwarding chain with paths, and whether
tests actually substitute the abstraction.

Replacement: inline the single implementation; collapse forwarding layers;
keep the abstraction only at true boundaries (network, storage, clock,
randomness, process execution).

## 4. Dead flexibility

Signals:

- Function parameters that every caller passes with the default value.
- Branches for modes no configuration enables.
- Feature flags that have been fully on (or off) everywhere for more than one
  release.
- Public functions with no callers outside tests written only to cover them.
- Exported settings documented nowhere and set nowhere.

Deciding question: can any current caller, configuration or deployment reach
this path?

Evidence: search results for callers and configuration values across the
repository and deployment manifests; flag state in every environment.

Replacement: remove the parameter, branch, flag or function, along with tests
that only exercised the removed path.

## 5. Indirection without payoff

Signals:

- Event buses or observers with one publisher and one subscriber in the same
  process.
- Configuration-driven behavior where the configuration lives next to the code
  and changes only with it.
- Runtime code generation (decorators, reflection, dynamic imports) to save a few lines
  of explicit code.
- Deep inheritance where composition or a plain function would do.

Deciding question: does a reader need to open more than two files to learn
what one call does? Is that cost paid back by real variation?

Evidence: the files a reader must open to trace one call, and the variation
the indirection supports in practice.

Replacement: a direct call, a plain data structure, an explicit list.

## 6. Defensive code for impossible states

Signals:

- Null or type checks on values that the type system or the immediate caller
  already guarantees.
- Catch-all exception handlers that log and continue past invariant
  violations.
- Validation repeated at every layer for the same input.

Deciding question: can this state actually occur given the validated boundary?
If it can, the check is behavior and stays. If it cannot, the check hides real
bugs by turning them into silent continuation.

Evidence: the boundary where the input is validated and the type or contract
that guarantees the invariant.

Replacement: validate once at the boundary; let internal violations fail loudly
with an assertion or a specific exception.

## 7. Dependency weight

Signals:

- A dependency used for one small function.
- Two dependencies that do the same job.
- A framework adopted for a feature the project uses in one place.

Deciding question: what does the dependency cost in install size, update
churn, security advisories and build time, compared with the code it saves?

Evidence: import sites, the functions used, and the native alternative.

Replacement: native API or a small local function with tests; remove from the
manifest and lockfile in the same change.

## What is not over-engineering

- Input validation, authorization checks and error handling at trust
  boundaries.
- Observability that someone queries: logs, metrics and traces with known
  consumers.
- Abstractions at genuine I/O boundaries that tests substitute.
- Compatibility layers with a dated removal plan and an owner.
- Code required by regulation, contract or a documented operational runbook.

## Sources

- [Python standard library](https://docs.python.org/3/library/index.html)
- [Python typing documentation](https://docs.python.org/3/library/typing.html)
- [Node.js API documentation](https://nodejs.org/api/)
- [MDN Web APIs](https://developer.mozilla.org/en-US/docs/Web/API)
