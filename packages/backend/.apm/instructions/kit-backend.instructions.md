---
description: Apply to Python domain, service, adapter, and transport code.
applyTo: "**/*.py"
---

- Keep domain logic independent of web, persistence, and provider frameworks; translate framework details at the outer boundary.
- Put use-case sequencing in application services, not routes or repositories; keep repositories to persistence operations.
- Keep route and command handlers thin: parse input, call one use case, and map its result and errors to the transport.
- Place provider clients behind a narrow adapter that owns timeout, retry, and error mapping; inject collaborators.
- Validate configuration at the boundary and pass only the fields a consumer reads.
- Follow existing package ownership; do not add layers that only forward arguments.
- Define domain-specific exception types and map them to transport status codes in one place.
- No broad catch with silent fallback or a success-shaped invalid-input result; preserve the originating failure.
- Make async I/O nonblocking; do not wrap synchronous work in an async signature or call blocking clients from the event loop. Bound retries and resource lifetimes, keep retries idempotent, propagate cancellation.
- Close clients, sessions, and files through context managers or lifespan hooks owned by the composition root.
- Paginate or stream unbounded collections; never load a whole table or file set into memory by default.
- Test protocols, errors, and public behavior with synthetic inputs rather than secrets.
- Use the `kit-python-service` skill for new services and adapters.
