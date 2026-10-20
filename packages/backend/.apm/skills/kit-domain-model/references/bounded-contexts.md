# Bounded contexts and context mapping

A bounded context is the boundary inside which one model and its ubiquitous
language apply consistently. The same word ("order", "account", "product") can
mean different things in different contexts, and that is acceptable as long as
each context is explicit.

## Identifying contexts

Look for:

- Terms that mean different things to different teams or features.
- Data that is owned and changed by one team but only read by others.
- Rules that change on different schedules or for different reasons.
- Separate deployment, storage, or scaling needs (strong but not required
  signals).

In a single codebase, a bounded context is usually a top-level package with its
own domain, application, and adapter modules. It does not need to be a separate
service.

## Context map relationships

| Relationship | Meaning | Typical code |
| --- | --- | --- |
| Shared kernel | Two contexts share a small, jointly owned model | A tiny shared package with strict review |
| Customer and supplier | Downstream needs drive upstream planning | Contract tests owned by downstream |
| Conformist | Downstream adopts upstream's model as is | Direct use of upstream types at the boundary |
| Anti-corruption layer | Downstream translates upstream's model | Adapter plus translator module |
| Open host service | Upstream publishes a protocol for many consumers | Versioned API or event schema |
| Published language | A documented shared exchange format | Schema files (OpenAPI, JSON Schema) |
| Separate ways | No integration; duplicate where needed | Nothing shared |

Record the map in the repository (a short document or diagram) and keep it
current when integration changes.

## Rules for code

- A context's domain package imports nothing from another context's domain.
- Cross-context calls go through ports in the calling context, implemented by
  adapters that translate (see [anti-corruption layer](anti-corruption-layer.md)).
- Shared identifiers cross the boundary as plain values (strings, UUIDs), not as
  the other context's entity.
- Integration events are a published contract; domain events stay internal.

The import rule can be enforced with a layer checker such as the backend wiring
checker in the `kit-python-service` skill, configured with one forbidden rule
per context pair.

## Ubiquitous language

- Use the domain experts' words in class, method, and event names.
- Keep a short glossary per context when terms are ambiguous across contexts.
- Rename code when the language changes; stale names cause real defects.

## Sources

- [Martin Fowler: Bounded Context](https://martinfowler.com/bliki/BoundedContext.html)
- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
- [Martin Fowler: Ubiquitous Language](https://martinfowler.com/bliki/UbiquitousLanguage.html)
- [Microsoft: Domain analysis for microservices](https://learn.microsoft.com/en-us/azure/architecture/microservices/model/domain-analysis)
