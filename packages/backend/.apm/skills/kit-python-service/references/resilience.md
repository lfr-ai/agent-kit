# Resilience: timeouts, retries, breakers, bulkheads, and load shedding

Facts verified as of 2026-10-27. Copy the primitives from
[resilience.py.template](../assets/resilience.py.template) and their
deterministic tests from
[test_resilience.py.template](../assets/test_resilience.py.template).

Resilience code lives in infrastructure adapters, around one remote call. The
adapter translates the final failure into the port's documented error (see
[error handling](error-handling.md)); the domain and application layers never
import retry or breaker types.

## Timeouts and deadlines

- Every remote call has a timeout. No exceptions for "fast" internal services.
- Distinguish a per-attempt timeout from the caller's overall deadline. The
  deadline covers every attempt and every backoff; an attempt never outlives it.
- `httpx` applies a 5 second default to each network operation (connect, read,
  write, pool acquisition) separately; it is not a total. Set an explicit
  `httpx.Timeout(...)` per client and wrap the whole call in
  `asyncio.timeout(...)` when you need a total bound.
- `asyncio.timeout(delay)` (Python 3.11+) cancels the enclosed work and raises
  `TimeoutError`; `asyncio.timeout_at(when)` takes an absolute loop time.
  Cancellation only interrupts at an `await`; blocking calls inside ignore it.
- Propagate the deadline instead of restarting the clock at each layer: the
  template binds it in a `ContextVar` (`deadline_scope`), and a nested scope
  can only shorten it. Pass the remaining budget to downstream services when
  the protocol supports it (gRPC deadlines); for internal HTTP calls send the
  remaining milliseconds in a documented header and cap what you accept.
- Order the timeout hierarchy from the inside out: database statement timeout
  (`kit-sql-persistence`) < HTTP client timeout < request deadline < server
  graceful timeout < proxy timeout (`kit-edge-networking`). The innermost
  component should fail first so the caller sees a precise error.

## Retries

Retry only when all of these hold:

1. The operation is idempotent (RFC 9110 section 9.2.2: safe methods, `PUT`,
   `DELETE`) or carries an idempotency key (`kit-api-contracts`).
2. The failure is transient: timeout, connection reset or refusal, `408`,
   `429`, `502`, `503`, `504`, or a driver error documented as retryable
   (serialization failure, deadlock). Never retry validation, authentication,
   authorization, or not-found outcomes.
3. A retry still fits in the deadline and the retry budget allows it.

Backoff is capped exponential with full jitter:
`delay = uniform(0, min(cap, base * 2 ** retry_number))`. Jitter spreads
synchronized clients so retries do not arrive as a second spike. When the
server sends `Retry-After`, wait that long instead, and give up when it
exceeds the policy cap. Bound attempts (3 is a common start) and total time.

Retry at one layer only. Three layers that each try three times turn one user
request into 27 calls to a struggling dependency. Choose the layer closest to
the failure that still knows whether the call is idempotent.

## Retry budgets

A per-call attempt limit does not stop a fleet from multiplying load during an
outage. Share a budget per dependency: `RetryBudget` follows the gRPC retry
throttling design, where each failure costs one token, each success earns
`token_ratio`, and retries stop while half or fewer of the tokens remain. AWS
SDKs apply a similar retry quota. Budgets make retries cheap when failures are
rare and nearly free of extra load when failures are common.

## Circuit breaker

| State | Calls | Transition |
| --- | --- | --- |
| Closed | Pass through; consecutive counted failures are tracked | Opens at `failure_threshold` |
| Open | Rejected immediately with `CircuitOpenError` | Half-open after `reset_timeout_seconds` |
| Half-open | Up to `half_open_max_calls` probes pass | Closes on a probe success; reopens on a probe failure |

- Count only failures that indicate an unhealthy dependency (timeouts,
  connection errors, 5xx). A not-found or validation error proves the
  dependency answered and counts as success.
- Keep one breaker per dependency instance and process; share it across calls.
- Never retry `CircuitOpenError` inside the same request; map it to the port's
  "unavailable" error and let the caller degrade (cached value, default, 503).
- Emit a metric or log line on every state change.

## Bulkheads and load shedding

- A bulkhead caps concurrent calls to one dependency so a slow dependency
  cannot consume every coroutine, connection, or thread. Use
  `asyncio.Semaphore` (the template's `Bulkhead`), connection pool limits
  (`httpx.Limits`, SQLAlchemy pool size), or a dedicated executor for blocking
  work.
- Shed load early: reject excess work at admission with 503 and `Retry-After`
  rather than queuing it until every request times out. Keep queues bounded;
  an unbounded queue converts overload into latency and memory exhaustion.
- Prioritize: shed background and retried work before interactive work.
- Per-caller fairness belongs to rate limiting (`kit-fastapi-service`); a
  bulkhead protects the dependency, not a caller.

## Hedging

Hedging sends a second copy of a slow request to another replica and uses the
first answer. It trims tail latency but adds load exactly when the system is
slow. Use it only for idempotent reads, only after a delay near the observed
95th percentile, with a retry budget, and cancel the loser. Never hedge writes
or calls with side effects.

## Where each consumer applies this

| Skill | Use |
| --- | --- |
| `kit-llm-client` | Per-attempt timeout plus overall deadline, retry `429` and `5xx` honoring `Retry-After`, a breaker and bulkhead per provider |
| `kit-task-queue` | Retries belong to the queue with backoff and a dead-letter path; the handler must not retry the same work again inside |
| `kit-caching` | Serve stale on dependency failure, protect the origin from stampedes, and bound cache calls with short timeouts |
| `kit-sql-persistence` | Retry a whole transaction only on serialization failures or deadlocks; set statement and lock timeouts; size the pool as a bulkhead |
| `kit-api-contracts` | Idempotency keys make non-idempotent writes safe to retry |

## Libraries versus the template

| Option | Status (2026-10) | Choose when |
| --- | --- | --- |
| `stamina` 26.1.0 | Active; opinionated wrapper around Tenacity with jittered exponential backoff, attempt and total-time limits, async support, instrumentation, and test helpers | You need retries only and want safe defaults |
| `tenacity` 9.2.1 | Active; general-purpose retry toolkit | You need custom stop, wait, or retry predicates |
| Template | Standard library only | You need a shared budget, breaker, bulkhead, and deadline integration without a dependency |

Whatever you choose, keep the policy (which errors, how many attempts, which
deadline) in the adapter and test it with an injected clock. Verify a breaker
library's maintenance status before adopting it.

## Testing

- Inject the clock, sleeper, and jitter; the fake sleeper advances the fake
  clock, so tests never wait. Stub jitter to return the ceiling for exact
  delays, and test the real jitter only for bounds.
- Use `asyncio.timeout(0)` with an operation that waits on an unset event to
  exercise the timeout path without real time.
- Cover: success after transient failures, immediate failure on a permanent
  error, exhausted attempts, deadline stop, budget stop, server hints, every
  breaker transition, and bulkhead shedding.
- In integration tests, inject faults at the adapter boundary (refused
  connection, slow response) rather than mocking the retry helper.

## Observability

- Count attempts and final outcomes per dependency (`success`, `retried`,
  `exhausted`, `deadline`, `circuit_open`, `shed`); record breaker state as a
  gauge. Label by dependency, never by user or request data
  (`kit-observability`).
- Log the final failure once at the boundary with the dependency name and
  attempt count; do not log every retry at warning level.

## Anti-patterns

| Anti-pattern | Consequence | Instead |
| --- | --- | --- |
| No timeout | One hung dependency exhausts every worker | Timeout plus deadline |
| Retrying non-idempotent writes | Duplicate orders or payments | Idempotency key or no retry |
| Fixed delay without jitter | Synchronized retry waves | Full jitter |
| Retries at every layer | Multiplied load during outages | One layer plus a budget |
| Breaker counting 4xx as failures | Healthy dependency marked down | Count transient failures only |
| Unbounded queue in front of a dependency | Latency and memory blow-up | Bulkhead and shedding |

## Sources

- [Python: asyncio timeouts](https://docs.python.org/3/library/asyncio-task.html#timeouts)
- [Python: asyncio.Semaphore](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore)
- [Python: contextvars](https://docs.python.org/3/library/contextvars.html)
- [HTTPX: Timeouts](https://www.python-httpx.org/advanced/timeouts/)
- [RFC 9110 section 9.2.2: Idempotent methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)
- [RFC 9110 section 10.2.3: Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
- [AWS Architecture Blog: Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- [Amazon Builders' Library: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)
- [AWS SDKs: Retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [gRPC proposal A6: Client retries and retry throttling](https://github.com/grpc/proposal/blob/master/A6-client-retries.md)
- [gRPC: Deadlines](https://grpc.io/docs/guides/deadlines/)
- [Azure Architecture Center: Retry pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry)
- [Azure Architecture Center: Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [Azure Architecture Center: Bulkhead pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
- [Google SRE book: Handling overload](https://sre.google/sre-book/handling-overload/)
- [Google SRE book: Addressing cascading failures](https://sre.google/sre-book/addressing-cascading-failures/)
- [stamina documentation](https://stamina.hynek.me/en/stable/)
- [Tenacity documentation](https://tenacity.readthedocs.io/en/latest/)
