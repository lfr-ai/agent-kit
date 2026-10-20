# Aggregates and invariants

An aggregate is a cluster of domain objects treated as one unit for state
changes. Its root is the only entry point, and everything inside it is
consistent when a command completes.

## Finding the boundary

1. List the invariants as sentences that must be true after every command, for
   example "an order's total equals the sum of its lines" or "a confirmed order
   has at least one line".
2. Group the state that each invariant reads. State that must change together
   in one transaction to keep an invariant true belongs in one aggregate.
3. Everything else is referenced by identifier and kept consistent eventually,
   through domain events or process managers.
4. Prefer small aggregates. A large aggregate serializes unrelated writes and
   causes lock contention or optimistic-concurrency conflicts.

## Design rules

- One repository per aggregate root; never load or save inner entities alone.
- Other aggregates are referenced by identifier (`customer_id: CustomerId`), not
  by object reference.
- Mutations go through intention-revealing methods (`add_line`, `confirm`,
  `cancel`) that check preconditions first, then change state, then record an
  event. No public setters for invariant fields.
- Methods either fully succeed or raise without changing state.
- Collections inside the aggregate are exposed as read-only views
  (`tuple(self._lines)`), never as the mutable internal list.
- Carry a `version` for optimistic concurrency; the repository rejects a save
  whose expected version is stale.
- Aggregate code imports no framework, ORM, or transport model.

## Invariants versus validation

| Kind | Example | Where it lives |
| --- | --- | --- |
| Value invariant | Quantity is positive | Value object constructor |
| Aggregate invariant | Total equals sum of lines | Aggregate root methods |
| Cross-aggregate rule | Customer credit limit across orders | Domain service or eventual policy |
| Input format | Field is a valid UUID string | Transport schema at the boundary |

Input-format validation at the boundary does not replace domain invariants; the
domain must stay correct even when called from a different transport.

## State transitions

Model status as a `StrEnum` and define allowed transitions in one table. A
transition method checks the table and raises a domain error naming the current
and requested state. Test every allowed transition and a representative set of
forbidden ones.

## Identity and equality

Aggregates compare by identity: two instances with the same identifier are the
same aggregate even when their state differs (for example before and after a
change). Implement `__eq__` and `__hash__` on the identifier only.

## Creation

Use a named factory (`Order.open(...)`) that enforces creation invariants and
records a creation event. Keep reconstitution from storage separate
(`Order.restore(...)`), so loading does not re-emit events or re-run creation
rules that may have changed since the record was written.

## Testing checklist

- [ ] Every invariant has a test that fails when the rule is removed.
- [ ] Every command method has a success test and a rejection test.
- [ ] A rejected command leaves state and pending events unchanged.
- [ ] Events are recorded with the correct payload and in order.
- [ ] Equality uses identity; hashing is stable across state changes.
- [ ] Property-based tests cover invariants over generated command sequences
      when the state space is large.

## Templates

[aggregate.py.template](../assets/aggregate.py.template) and
[test_aggregate.py.template](../assets/test_aggregate.py.template).

## Sources

- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
- [Martin Fowler: DDD Aggregate](https://martinfowler.com/bliki/DDD_Aggregate.html)
- [Vaughn Vernon: Effective Aggregate Design](https://www.dddcommunity.org/library/vernon_2011/)
- [Microsoft: Design a microservice domain model](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/microservice-domain-model)
