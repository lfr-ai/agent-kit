# Domain events

A domain event records that something meaningful happened in the domain, named
in the past tense: `OrderConfirmed`, `InvoiceIssued`, `PaymentFailed`.

## When to raise one

- Another aggregate or bounded context must react (eventual consistency).
- The business wants an audit trail of state changes.
- A side effect (email, projection update) must not run inside the aggregate.

Do not raise events for every setter; raise them for business facts.

## Shape

```python
@dataclass(frozen=True, kw_only=True, slots=True)
class OrderConfirmed:
    event_id: UUID
    occurred_at: datetime
    order_id: OrderId
    total: Money
```

- Immutable, past-tense name, and self-contained: a handler should not need to
  load the aggregate to understand the fact.
- Include the identifier of the aggregate and the minimum data consumers need.
- Include `event_id` for de-duplication and `occurred_at` (timezone-aware) for
  ordering and audit.
- Do not include secrets or unnecessary personal data; events are often stored
  and replicated widely.

## Recording and dispatching

1. Aggregate methods append events to a private pending list.
2. The application service saves the aggregate and then collects its pending
   events (`pull_events()` returns and clears them).
3. A dispatcher delivers events to in-process handlers or an outbox.

For cross-process delivery, write events to an outbox table in the same
transaction as the aggregate, and publish from the outbox afterwards. This
avoids the "saved but not published" and "published but not saved" failure
modes of dual writes.

## Handlers

- Handlers are idempotent: delivery is at least once, so the same `event_id`
  may arrive twice.
- A handler changes at most one aggregate per transaction.
- Handler failures are retried with backoff and moved to a dead-letter store
  after a bounded number of attempts.

## Domain events versus integration events

A domain event is internal to a bounded context and may change with the model.
An integration event is a published contract for other contexts; version it,
keep it backwards compatible, and translate from domain events at the
boundary.

## Testing

- The aggregate records the expected event, with the expected payload, exactly
  once per successful command, and none on rejection.
- `pull_events()` clears pending events.
- Handlers are tested with duplicate delivery.

## Template

[domain_event.py.template](../assets/domain_event.py.template).

## Sources

- [Martin Fowler: Domain Event](https://martinfowler.com/eaaDev/DomainEvent.html)
- [Microsoft: Domain events design and implementation](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/domain-events-design-implementation)
- [Microsoft: Transactional outbox pattern](https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-outbox-cosmos)
- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
