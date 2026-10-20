# Domain modeling guide

## Purpose

A concise path through the domain-modeling references for someone starting a
new model or reviewing a change to an existing one.

## Order of work

1. Language: collect the terms, their meanings, and their owning context
   ([bounded contexts](references/bounded-contexts.md)).
2. Invariants: write them as testable sentences
   ([aggregates and invariants](references/aggregates-invariants.md)).
3. Values: extract value objects for rules and units
   ([value objects](references/value-objects.md)).
4. Aggregates: draw consistency boundaries and transition methods.
5. Events: name the facts other parts react to
   ([domain events](references/domain-events.md)).
6. Ports: declare repositories and external services in domain language
   ([repositories as ports](references/repositories-ports.md),
   [anti-corruption layer](references/anti-corruption-layer.md)).
7. Tests: invariants, transitions, events, identity, and contract tests shared
   by every adapter.

## Acceptance gates

- Domain types have clear identity semantics (entities) or value equality
  (value objects).
- Invariants are enforced at construction or through explicit factories and
  command methods.
- Conversion boundaries to persistence and transport are implemented in
  adapters and tested.
- [check_port_adapter_binding.py](assets/check_port_adapter_binding.py) reports
  no unbound port.

## Failure modes

- Inconsistent equality or identity leading to duplicate records or cache misses.
- Mutable value objects that leak invariants.
- Hidden dependencies on ORM behavior or transport-specific fields.

## Negative cases

- Invalid states passed through factory functions and accepted silently.
- Boundary conversions that drop required invariants or misinterpret units or
  time zones.
- Unknown codes from a foreign system mapped to a default value.

## Recovery

- Add an adapter layer that reads old persisted shapes and normalizes them into
  current domain types.
- Provide migration utilities that detect and repair inconsistent persisted
  records, tested against representative old data.

## Scope and limits

This guide covers modeling patterns and testable invariants. It does not
prescribe persistence technology or runtime performance characteristics.

## Sources

- [Martin Fowler: Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- [Martin Fowler: Value Object](https://martinfowler.com/bliki/ValueObject.html)
- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
