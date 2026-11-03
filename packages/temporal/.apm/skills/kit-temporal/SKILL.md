---
name: kit-temporal
description: Use when building or reviewing Temporal workflows, Activities, workers, retries or replay tests.
license: MIT
---

# Keep durable execution replay-safe

## Procedure

1. Read the [runtime and source guide](references/guide.md). Use Python first;
   TypeScript is an alternative, not a second implementation. Do not install
   SDKs into this toolkit or assume Bun can run the TypeScript worker.
2. Define the workflow input/result and domain errors as small typed records.
   Keep only orchestration in `@workflow.defn` / `@workflow.run`; use
   `@activity.defn` for network, model, database and tool calls.
3. Use SDK workflow time, randomness, sleeps and wait conditions. No environment
   reads, blocking code, ordinary clock/random, unmanaged tasks or I/O in
   workflows. Sandbox pass-through is not a determinism exemption.
4. Configure explicit Activity start-to-close and schedule-to-close timeouts,
   finite retries, heartbeat for long work and a business deadline. Adapt the
   [stdlib policy preflight](assets/execution_policy.py); it does not simulate
   Temporal scheduling or guarantee every configured attempt can finish.
5. Classify permanent failures as non-retryable `ApplicationError` types.
   Translate vendor errors in Activities with `raise ... from error`; let the
   workflow handle `ActivityError` deliberately. Do not stringify vendor bodies.
6. Make effects idempotent with a stable business-operation key and transactional
   uniqueness/outbox or provider idempotency. A timeout may mean the effect
   committed. Neither workflow IDs nor retry attempt numbers provide exactly-once
   external execution. Adapt the [pure effect decision](assets/effect_policy.py.template)
   inside the destination's atomic receipt/effect boundary, not as a local lock.
7. Heartbeat progress for resumable Activities; propagate cancellation and await
   cleanup. A timed-out or cancelled synchronous Activity may still run. Bound
   compensation separately; never swallow cancellation to report success.
8. Use direct SDK signal/update/query decorators for narrow state transitions.
   Queries are read-only; update validators are deterministic and side-effect
   free. Ingress authenticates and authorizes before issuing a signal/update;
   revalidate resource permissions at effect time.
9. Choose Worker Deployment Versioning: Pinned for finite runs kept on one
   deployment version, Auto-Upgrade only with replay-safe changes/patching.
   Record draining, rollback and old-history retention; use Continue-As-New to
   bound history without losing operation keys.
10. Run the original [SDK behavioral tests](assets/test_temporal_behavior.py.template)
    in a consumer with its reviewed SDK/test server. Add heartbeat cancellation,
    destination idempotency and old-history replay cases from the guide. Syntax
    checks and stdlib tests are not SDK execution.
11. Secure namespace access, TLS and credentials; use payload codecs where
    required, knowing routing metadata is not encrypted by a payload codec.
    Log failures once at the handling boundary using safe operation codes;
    replay-aware workflow logs do not authorize personal-data capture.
12. Record focused test commands, SDK/server versions, replay corpus and which
    vendor runtime checks actually ran. MCP documentation access is read-only
    research, never authorization to operate Temporal resources.

## Acceptance gates

- Activities own all nondeterministic I/O; no prompt or credential enters history.
- Timeout/retry budgets, persistent idempotency and cancellation are tested.
- Representative historical executions replay on the proposed workflow code.
- Worker promotion, draining and rollback are reviewed independently of tests.
