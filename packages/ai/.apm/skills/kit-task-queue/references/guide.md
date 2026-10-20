# Task queue guide

## Purpose

Design recoverable background work with explicit delivery semantics,
idempotent handlers, bounded retries, dead-letter handling, and operator
tooling. This guide maps the references and copyable assets of the skill.

## References

| Topic | Reference |
| --- | --- |
| At-least-once delivery, idempotency keys, outbox, ordering, payloads | [delivery-semantics.md](delivery-semantics.md) |
| Failure classification, backoff with jitter, dead letters, poison messages, replay | [retries-and-dead-letter.md](retries-and-dead-letter.md) |
| Visibility timeouts, timeout hierarchy, scheduling, fairness, shutdown | [leases-and-scheduling.md](leases-and-scheduling.md) |
| Metrics, tracing, runbooks, operator tooling | [observability-and-operations.md](observability-and-operations.md) |
| SQS, RabbitMQ, Redis Streams, Service Bus and Celery mapping | [broker-mapping.md](broker-mapping.md) |

## Assets and copy targets

| Asset | Copy to | Purpose |
| --- | --- | --- |
| [task_contracts.py.template](../assets/task_contracts.py.template) | `tasks/contracts.py` | Envelope, errors, broker and idempotency ports |
| [worker.py.template](../assets/worker.py.template) | `tasks/worker.py` | Delivery policy: idempotency, leases, retries, dead letters |
| [in_memory_broker.py.template](../assets/in_memory_broker.py.template) | `tasks/memory.py` | Lease-accurate fakes for tests and local runs |
| [celery_app.py.template](../assets/celery_app.py.template) | `tasks/adapters/celery_app.py` | Celery binding with at-least-once settings |
| [test_worker.py.template](../assets/test_worker.py.template) | `tests/tasks/` | Duplicate, crash, lease, retry, dead-letter and shutdown tests |
| [test_task_contracts.py.template](../assets/test_task_contracts.py.template) | `tests/tasks/` | Envelope validation and parsing |
| [queue_template.json.template](../assets/queue_template.json.template) | fixture | Sample envelopes in the contract format |
| [verify_queue_messages.py](../assets/verify_queue_messages.py) | run in place or in CI | Validates envelope samples and dead-letter exports |

Validate samples before replay or in CI:

```text
python verify_queue_messages.py samples.json --supported invoice.render:1 [--max-bytes N] [--allow-duplicate-keys]
```

It prints `path:line: message` per finding and exits 1 on findings, 2 on
unreadable input or bad arguments.

## Acceptance gates

- Envelope carries task id, task type, version, business-derived idempotency
  key, timezone-aware creation time, and correlation id; payloads hold
  references, not secrets.
- Handlers are idempotent by key; a duplicate-delivery test proves the side
  effect runs once.
- Leases exceed handler timeouts and are renewed for long work.
- Retryable and permanent failures are classified; retries are bounded with
  jittered backoff; permanent failures dead-letter immediately.
- Dead-letter queue, alerting, and a replay procedure exist for every queue.
- Metrics include oldest-message age, outcomes per task type, and dead-letter
  arrivals.

## Failure modes

- Unbounded retries causing duplicate side effects or cost.
- Poison messages repeatedly failing and consuming worker capacity.
- Leases shorter than processing time producing concurrent duplicates.
- Missing correlation ids preventing diagnosis.
- Exactly-once assumed from a broker feature that does not cover side effects.

## Negative cases

Duplicate delivery, worker crash before acknowledgement, lost lease,
exhausted retries, permanent failure, malformed body, incompatible version,
handler timeout, replay of completed work, and shutdown with work in flight.

## Scope and limits

The assets validate the message contract and worker policy with an
in-memory broker. They do not certify a broker's configuration, throughput, or
delivery guarantees at scale; run the same contract tests against the real
adapter and a load test before launch.

## Sources

- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html)
- [RabbitMQ documentation](https://www.rabbitmq.com/docs)
