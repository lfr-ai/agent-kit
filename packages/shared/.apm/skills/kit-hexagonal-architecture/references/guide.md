# Protect policy from external details

## Trace dependencies and effects

Map a real request from presentation to application policy, domain behavior,
adapter effect and composition. Source imports and runtime calls are different
graphs: an injected adapter can execute outward while its interface points
inward. Name the business invariant before introducing a port.

| Responsibility | Should own | Should not own |
| --- | --- | --- |
| Domain | invariants and value semantics | HTTP, database sessions, environment |
| Application | use-case orchestration, transaction intent | concrete clients or CLI printing |
| Infrastructure | files, network, persistence adapters | product policy hidden in mappings |
| Presentation | parsing, response/error translation | transaction or business rules |
| Composition | constructing and wiring collaborators | duplicated policy |

Adapt this map to actual repository conventions. A function is often a sufficient
port; add a Protocol when it isolates a meaningful replaceable dependency.

## Quality gates

- Domain policy is testable without network, database or environment access.
- Import contracts reject a deliberate outward dependency.
- Adapter contract tests pin serialization, error translation and transactions.
- Composition tests resolve the real use case; a matching class name is not DI proof.
- The installed package works away from its checkout.

## Failure and recovery

Do not relocate an ORM type into Core merely to make imports shorter. Do not
invent a global dependency container or pass an untyped service locator through
every layer. If separation would break a public contract, first characterize
that contract, then migrate one boundary with regression coverage.
Static import checks cannot prove behavioral substitutability or correct wiring.

## Deeper references

- [Ports, adapters and the dependency rule](ports-and-adapters.md)
- [Use cases and the composition root](use-cases-and-composition.md)
- [Mapping between layers and transaction boundaries](mapping-and-transactions.md)
- [Testing with fakes and contract tests](testing-with-fakes.md)
- [Anti-patterns and repairs](anti-patterns.md)

## Sources

- Alistair Cockburn, [Hexagonal architecture](https://alistair.cockburn.us/hexagonal-architecture/)
