---
name: kit-domain-model
description: Use when modeling domain entities, value objects, and invariants independently of transport and persistence.
license: MIT
---

# Express domain rules in domain types

## Procedure

1. Start from business language, identity, lifecycle, and invariants already
   used by the project. Reuse existing names; record ambiguous terms per
   [bounded contexts](references/bounded-contexts.md).
2. Write each invariant as one sentence that is true or false for one object.
   Decide where it lives with the table in
   [aggregates and invariants](references/aggregates-invariants.md).
3. Distinguish entities by stable identity; use
   [value objects](references/value-objects.md) for immutable concepts compared
   by value (money, quantities, identifiers with a format, date ranges).
4. Draw the aggregate boundary around state that one command must change
   atomically. Reference other aggregates by identifier only.
5. Make invalid states impossible to represent: validate in constructors or named
   factories, expose read-only collections, and change state only through
   intention-revealing methods that check preconditions first.
6. Represent units, currencies, time zones, and optionality explicitly rather
   than as ambiguous primitives.
7. Model state transitions as methods that either fully succeed or raise a
   domain error without changing state, and record a
   [domain event](references/domain-events.md) for facts others react to.
8. Declare persistence as a repository port in domain language per
   [repositories as ports](references/repositories-ports.md); keep ORM rows,
   HTTP schemas, and SDK types in adapters.
9. Translate foreign models through an
   [anti-corruption layer](references/anti-corruption-layer.md) instead of
   importing them into the domain.
10. Test invariants, transition rejection, event emission, and equality or
    identity semantics without external resources; add property-based tests for
    invariants over large input spaces.
11. Run [check_port_adapter_binding.py](assets/check_port_adapter_binding.py)
    so every port has at least one complete adapter, then the project gate.
12. Avoid adding an entity or abstraction for data that has no identity or
    domain behavior.

## Acceptance gates

- Every invariant has a test that fails when the rule is removed.
- Value objects are frozen, keyword-only, and slotted; aggregates compare and
  hash by identity only.
- Rejected commands leave state and pending events unchanged.
- Domain modules import no framework, ORM, transport schema, or provider SDK.
- Every repository or service port in the core has at least one adapter
  implementing all its members, and the in-memory and production adapters pass
  the same contract tests.
- Persisted-shape changes have a migration or read adapter with tests.

## Failure modes

- Ambiguous identity leading to duplicate records or cache misses.
- Mutable value objects or exposed internal lists that bypass invariants.
- Aggregates so large that unrelated writes conflict.
- Hidden coupling to ORM lazy loading or transport-specific fields.
- Events published before the aggregate is saved (dual-write inconsistency).

## Recovery

- Add migration adapters that translate persisted representations to updated
  domain shapes; keep backward read adapters while old data exists.
- Split an oversized aggregate by moving a cross-object rule to a domain event
  handler with eventual consistency, after confirming the business accepts it.

## Templates

| Template | Tests |
| --- | --- |
| [value_object.py.template](assets/value_object.py.template) | [test_value_object.py.template](assets/test_value_object.py.template), [test_value_object_properties.py.template](assets/test_value_object_properties.py.template) (Hypothesis) |
| [aggregate.py.template](assets/aggregate.py.template) | [test_aggregate.py.template](assets/test_aggregate.py.template) |
| [domain_event.py.template](assets/domain_event.py.template) | covered by the aggregate tests |
| [repository_port.py.template](assets/repository_port.py.template) | [test_in_memory_repository.py.template](assets/test_in_memory_repository.py.template) |
| [in_memory_repository.py.template](assets/in_memory_repository.py.template) | same contract suite |

Templates use the placeholder package `shop`; rename imports when copying.

## Binding checker

```text
python check_port_adapter_binding.py --core src/shop/core --adapters src/shop/infrastructure
python check_port_adapter_binding.py --core src/shop/core --adapters src/shop/infrastructure \
    --adapters tests/fakes --ignore "^Clock$"
```

Prints `path:line: message` per unbound port and exits 1 on findings.

## References

- [Domain modeling guide](guide.md) and [checklist](references/guide.md)
- [Aggregates and invariants](references/aggregates-invariants.md)
- [Value objects](references/value-objects.md)
- [Domain events](references/domain-events.md)
- [Repositories as ports](references/repositories-ports.md)
- [Bounded contexts and context mapping](references/bounded-contexts.md)
- [Anti-corruption layer](references/anti-corruption-layer.md)
