# Anti-corruption layer

An anti-corruption layer (ACL) translates between your model and a foreign
model (a legacy system, a third-party API, another bounded context) so the
foreign concepts, names, and quirks do not leak into your domain.

## When to use one

- The upstream model is shaped for a different purpose or uses conflicting
  terms.
- The upstream is unstable, poorly documented, or outside your control.
- You are migrating away from a legacy system and want new code to stay clean.

Skip it when the upstream model already matches yours closely (conformist) and
the cost of translation exceeds the risk of coupling.

## Structure

```text
core/ports.py            CatalogPort (Protocol) in your language
infrastructure/catalog/
  client.py              transport client for the foreign API (HTTP, SDK)
  schema.py              foreign payload shapes, parsed and validated
  translator.py          pure functions: foreign shape <-> domain types
  adapter.py             implements CatalogPort using client + translator
```

- The port is declared in your terms (`product_price(sku) -> Money | None`).
- The client knows the wire protocol only.
- The translator is pure and fully unit-tested with recorded payloads.
- The adapter composes client and translator and converts vendor errors into
  the port's documented errors.

## Translation rules

- Map every foreign enum or code explicitly; unknown values raise a
  translation error or map to an explicit `UNKNOWN` member, never silently to a
  default.
- Convert units, currencies, time zones, and identifiers at the boundary.
- Reject or quarantine payloads that violate your invariants instead of
  creating invalid domain objects.
- Keep translation lossless where the domain needs the data; drop only fields
  the domain does not use.

## Failure handling

- Timeouts, retries, and circuit breaking belong to the client or adapter.
- The adapter raises port-level errors (`CatalogUnavailableError`) chained from
  vendor errors.
- Cache or fall back only when the domain explicitly accepts stale data.

## Testing

- Translator: table-driven unit tests over recorded foreign payloads, including
  malformed and unknown-code cases.
- Adapter: contract tests against a fake server or recorded responses.
- Domain and application: use an in-memory implementation of the port.

## Sources

- [Microsoft: Anti-corruption Layer pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer)
- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
- [Martin Fowler: Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html)
