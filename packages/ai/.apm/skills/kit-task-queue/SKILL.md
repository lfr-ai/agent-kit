---
name: kit-task-queue
description: Use when designing background task submission and workers with bounded retries and explicit delivery semantics.
license: MIT
---

# Make queued work recoverable

## Procedure

1. Define task identity, payload schema and version, owner, completion
   meaning, and delivery guarantee; assume at-least-once delivery
   ([delivery-semantics.md](references/delivery-semantics.md)).
2. Use a versioned envelope with a business-derived idempotency key and a
   correlation id ([task_contracts.py.template](assets/task_contracts.py.template)).
3. Keep payloads minimal; store sensitive material behind the approved
   protected data boundary and pass references.
4. Enqueue through a transactional outbox when tasks follow database changes.
5. Validate and version messages at enqueue and worker boundaries; deploy
   consumers of a new version before producers emit it.
6. Make handlers idempotent: claim the key, run, mark done, then acknowledge;
   pass the key to downstream systems
   ([worker.py.template](assets/worker.py.template)).
7. Set leases longer than handler timeouts and renew them for long work;
   align the full timeout hierarchy
   ([leases-and-scheduling.md](references/leases-and-scheduling.md)).
8. Classify retryable versus permanent errors; retry with bounded, jittered
   exponential backoff
   ([retries-and-dead-letter.md](references/retries-and-dead-letter.md)).
9. Configure a dead-letter queue, poison-message limits, alerting on arrivals,
   and an operator replay procedure.
10. Bound queue depth, worker concurrency, payload size, per-task runtime, and
    per-tenant share; run exactly one scheduler with slot-derived keys.
11. Make cancellation, shutdown, and partial side effects explicit per task type.
12. Emit content-free lifecycle logs and metrics with correlation ids,
    including oldest-message age
    ([observability-and-operations.md](references/observability-and-operations.md)).
13. Map the port onto the chosen broker
    ([broker-mapping.md](references/broker-mapping.md),
    [celery_app.py.template](assets/celery_app.py.template)) and run the same
    contract tests against it and the
    [in-memory broker](assets/in_memory_broker.py.template).
14. Test duplicate delivery, worker crash, lost leases, exhausted retries,
    permanent failures, incompatible versions, and replay
    ([test_worker.py.template](assets/test_worker.py.template),
    [references/guide.md](references/guide.md)).
15. Validate samples and dead-letter exports with
    [verify_queue_messages.py](assets/verify_queue_messages.py) against
    [queue_template.json.template](assets/queue_template.json.template).

## Acceptance gates

- Message schema versioning present; incompatible versions dead-letter.
- Duplicate delivery runs side effects once, proven by a test.
- Retries are bounded and jittered; permanent errors are never retried.
- Dead-letter policy, alerts, and replay procedure are documented.
- Lease, handler, and downstream timeouts are consistent and tested.
- Metrics expose backlog age, outcomes, and dead-letter arrivals.

## Failure modes

- Exactly-once execution assumed without proof across every side effect.
- Poison messages consuming worker capacity indefinitely.
- Secrets or large documents carried in payloads.
- Scheduled jobs duplicated by multiple schedulers.
