# Domain model review checklist

## Purpose

Checklist for reviewing a domain model change: deterministic invariants and
explicit conversion boundaries. Topic detail lives in the sibling references.

## Acceptance gates

- Value objects are immutable with clear equality semantics
  ([value objects](value-objects.md)).
- Invariants are enforced at construction, via named factory methods, or in
  aggregate command methods ([aggregates](aggregates-invariants.md)).
- Conversion adapters document the mapping to transport and persistence shapes
  ([repositories](repositories-ports.md),
  [anti-corruption layer](anti-corruption-layer.md)).
- Events are past-tense, immutable, and recorded only on success
  ([domain events](domain-events.md)).

## Review questions

| Question | Evidence |
| --- | --- |
| Is each invariant a testable sentence with a failing-when-removed test? | Test name per invariant |
| Does one command change exactly one aggregate? | Application service code |
| Are other aggregates referenced by identifier only? | Field types |
| Do rejected commands leave no state or events behind? | Rejection tests |
| Does the domain import only the standard library and domain modules? | Import check |
| Does every port have a complete adapter and a shared contract suite? | Binding checker, contract tests |
| Are foreign codes mapped explicitly, including unknown values? | Translator tests |

## Failure modes

- Ambiguous identity leading to duplicate entities.
- Unenforced invariants allowing invalid states to exist.
- Contexts sharing domain classes instead of identifiers or published contracts
  ([bounded contexts](bounded-contexts.md)).

## Verification prerequisites

- Unit tests covering constructor invariants and state transitions.
- Property-based tests for invariants over large input spaces.
- Migration adapter tests for persisted representation changes.

## Scope and limits

This checklist covers modeling and authoring tests. It does not perform
migrations or verify runtime performance.

## Sources

- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
- [Martin Fowler: Bounded Context](https://martinfowler.com/bliki/BoundedContext.html)
