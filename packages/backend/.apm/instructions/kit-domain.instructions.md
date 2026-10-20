---
description: Apply to domain and core business-policy modules.
applyTo: "**/domain/**/*.py,**/core/**/*.py"
---

- Keep domain decisions independent of web, database, queue, and provider frameworks.
- Encode invariants in constructors and domain operations so an invalid object cannot exist.
- Model valid state transitions explicitly and reject illegal transitions with a domain error.
- Represent units, money, identities, and optional values with dedicated value types instead of bare primitives.
- Compare entities by identity and value objects by value; keep value objects immutable.
- Change an aggregate only through its root, and modify one aggregate per transaction.
- Name types and operations in the business language used by specifications and conversations.
- Use concrete return and error types; do not turn invalid state into a success-shaped default.
- Publish domain events for facts other components react to instead of calling those components directly.
- Translate external representations in adapters rather than importing them into core policy.
- Inject time, randomness, and identifier generation so domain rules stay deterministic.
- Test business outcomes without requiring infrastructure.
- Use the `kit-domain-model` skill for modeling aggregates and invariants.
