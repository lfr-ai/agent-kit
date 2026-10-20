# Leases, timeouts, scheduling, and shutdown

## Visibility timeouts and leases

When a worker receives a message, the broker hides it for a visibility timeout
(a lease). If the worker does not acknowledge in time, the message becomes
visible again and another worker processes it.

- The lease must exceed the handler's normal runtime. For long or variable
  work, extend the lease periodically while the handler runs (the template
  worker renews every `renew_every_s`, which must be well below the lease).
- The handler timeout (`HandlerSpec.timeout_s`) must be shorter than what the
  lease can cover, so the worker stops work it can no longer own.
- If a lease is lost anyway, acknowledging fails (`LeaseLostError`) because
  another worker owns the message; the idempotency store keeps the duplicate
  harmless.
- Prefetch or batch size multiplies lease pressure: messages waiting in a
  worker's local buffer age while invisible to others. Keep prefetch low for
  long tasks.

## Timeout hierarchy

| Timeout | Must be | Template |
| --- | --- | --- |
| Downstream call timeout | Shorter than the handler timeout | Set in each adapter |
| Handler timeout | Shorter than lease coverage | `HandlerSpec.timeout_s` |
| Lease (visibility) | Longer than the renewal interval and the normal runtime | `WorkerSettings.visibility_timeout_s` |
| Idempotency lease | Longer than handler timeout, so duplicates wait | `WorkerSettings.idempotency_lease_s` |
| Graceful shutdown window | Longer than the handler timeout, or in-flight work is abandoned | Process manager setting |

## Delayed and scheduled work

- Delays: use the broker's delay or a not-before time; long delays may exceed
  broker limits, so store far-future work in a database and enqueue it when due.
- Periodic jobs: run exactly one scheduler (leader-elected or a managed
  scheduler); multiple schedulers enqueue duplicates. Give each run an
  idempotency key derived from the schedule slot, for example
  `report.daily:2026-01-01`, so duplicates and catch-up runs are harmless.
- Decide catch-up behavior after downtime: run every missed slot, only the
  latest, or none. Write it down per job.
- Express schedules in UTC and test daylight-saving boundaries if business
  schedules use local time.

## Concurrency, priority, and fairness

- Bound worker concurrency by the scarcest dependency (database connections,
  API rate limits), not by CPU count.
- Separate queues for latency-sensitive and bulk work so a backlog of bulk
  tasks cannot starve interactive ones.
- For multi-tenant workloads, cap in-flight tasks per tenant or shard queues
  so one tenant cannot monopolize workers.
- Bound queue depth or producer rate; reject or shed load at enqueue time with
  a clear error instead of building an unbounded backlog.

## Cancellation and shutdown

- On shutdown, stop receiving, let in-flight handlers finish within the
  window, and leave unfinished messages unacknowledged so they reappear (the
  template's `Worker.run` loop stops at the next batch boundary).
- Task cancellation by users is a state change: record it, and have handlers
  check it at safe points; do not rely on killing worker processes.
- Partial side effects must be either idempotent on retry or compensated
  explicitly; document which for each task type.

## Sources

- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Azure Service Bus: message locks and settlement](https://learn.microsoft.com/en-us/azure/service-bus-messaging/message-transfers-locks-settlement)
- [RabbitMQ consumer prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)
- [Celery configuration: broker_transport_options and visibility timeout](https://docs.celeryq.dev/en/stable/userguide/configuration.html)
- [Celery periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html)
