---
name: kit-hexagonal-architecture
description: Use when defining or reviewing Hexagonal Architecture (Ports and Adapters) boundaries in a layered application core.
license: MIT
---

# Hexagonal boundaries and dependency inversion

## Procedure

1. Identify the policy that should remain stable as external technologies change.
   Write the business invariant in one sentence before drawing any boundary.
2. Map the outside actors and technologies to adapters around the application core:
   driving (CLI, HTTP, workers, tests) and driven (storage, providers, mail, clock).
   Use the [boundary worksheet](assets/boundaries.md.template).
3. Treat a port as an interaction API; an ordinary use-case call is a driving port.
   Declare a `Protocol` only for driven collaborators that do I/O or need
   substitution. See [ports and adapters](references/ports-and-adapters.md).
4. Name ports after intent, keep parameters and results in domain or port-owned
   types, and define port exceptions classified by caller action
   ([client port](assets/payment_gateway_port.py.template),
   [port errors](assets/payment_errors.py.template),
   [repository port](assets/invoice_repository_port.py.template),
   [notifier port](assets/notification_port.py.template)).
5. Keep source dependencies pointed toward policy. Encode the rule as an import
   contract ([Import Linter template](assets/importlinter.ini.template)) and prove
   it fails on a deliberate outward import.
6. Model policy with functions, data structures, or domain types as the rules need
   ([domain example](assets/invoice.py.template)). Validate invariants on
   construction so mapped data is checked at the boundary.
7. Write use cases as plain classes or functions that receive ports by keyword,
   own the transaction and order of effects, and return result objects
   ([use case](assets/use_case.py.template),
   [use cases and composition](references/use-cases-and-composition.md)).
8. Implement driven adapters that own wire formats, timeouts and error translation
   ([HTTP client adapter](assets/http_payment_gateway.py.template),
   [SQLite repository adapter](assets/invoice_repository_adapter.py.template),
   [SMTP adapter](assets/smtp_notifier.py.template)). Map rows and payloads in the
   adapter only ([mapping and transactions](references/mapping-and-transactions.md)).
9. Add a Unit of Work only when a use case changes more than one record and partial
   success would be wrong; place non-repeatable remote effects behind idempotency
   keys and notifications after commit.
10. Wire everything in one [composition root](assets/composition.py.template); no
    other module imports adapters or reads configuration.
11. Test policy through [fakes](assets/fake_adapters.py.template) and assert outcomes
    ([use-case tests](assets/test_use_case.py.template)). Run one contract suite
    against fake and real adapters
    ([repository contract](assets/test_repository_contract.py.template),
    [client contract](assets/test_payment_contract.py.template),
    [testing guidance](references/testing-with-fakes.md)).
12. Check port/adapter signatures statically with
    [`check_ports_adapters.py`](assets/check_ports_adapters.py)
    (`python check_ports_adapters.py src tests --ports <ports package>`).
13. Remove indirection that only renames a call or forwards every argument, and
    review the [anti-patterns](references/anti-patterns.md).
14. Record constraints and the boundary that owns each trade-off.

Rich entity classes, separate Protocol declarations, Unit of Work abstractions,
and exact layer folders are not qualification checklists. Treat Pydantic or
configuration coupling as an explicit isolation trade-off, not an automatic
architecture failure. Adapt package names to the actual project conventions.

## Acceptance gates

- Domain and use-case tests run without network, database files or environment
  variables, using fakes that pass the same contract suite as the real adapters.
- The import contract passes and was shown to fail on a deliberate violation.
- `check_ports_adapters.py` reports no findings, or each remaining finding is a
  recorded, justified `--allow-extra`/`--skip` decision.
- Every port exception is raised by at least one adapter test for each documented
  failure class (decline, transient, protocol drift, not found, duplicate).
- Exit without commit discards changes in every unit-of-work implementation.
- One composition test builds the real graph with safe settings and runs a use case.
- The installed package works away from its checkout.

Static checks prove shape and direction, not behavior or correct wiring; keep
the contract and composition tests. Start with the
[boundary checks](references/guide.md).
