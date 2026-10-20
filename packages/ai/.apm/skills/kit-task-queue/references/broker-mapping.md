# Mapping the contract onto brokers

The neutral `Broker` port in
[task_contracts.py.template](../assets/task_contracts.py.template) names the
operations every adapter must provide. This table maps them onto common
brokers so adapters stay thin and behavior stays consistent.

| Port operation | Amazon SQS | RabbitMQ | Redis Streams | Azure Service Bus | Celery |
| --- | --- | --- | --- | --- | --- |
| `enqueue(delay_s)` | SendMessage with DelaySeconds (limited range) | Publish; delay via a delayed-message plugin or TTL plus dead-letter exchange | XADD; delay needs a sorted set or scheduler | Send with ScheduledEnqueueTime | `apply_async(countdown=...)` |
| `receive(visibility)` | ReceiveMessage with VisibilityTimeout | Consume with manual acks and prefetch | XREADGROUP into a consumer group (pending entries list) | Receive in peek-lock mode | Worker with `task_acks_late` and prefetch multiplier |
| `ack` | DeleteMessage with the receipt handle | basic.ack | XACK | Complete | Automatic after task returns (late ack) |
| `retry(delay_s)` | ChangeMessageVisibility to the delay | Nack and republish with delay | Leave pending, reclaim later with XAUTOCLAIM | Abandon, or reschedule a copy | `autoretry_for` with backoff and jitter |
| `extend(visibility)` | ChangeMessageVisibility | Not needed while the channel is open (consumer timeout applies) | Re-claim to reset idle time | RenewMessageLock | Transport visibility timeout must cover runtime |
| `dead_letter(reason)` | Redrive policy after maxReceiveCount, or send to a DLQ explicitly | Reject without requeue to a dead-letter exchange | XADD to a dead-letter stream, then XACK | DeadLetter with reason | `Reject(requeue=False)` plus broker dead-letter config |
| Delivery count | ApproximateReceiveCount attribute | Delivery count header on quorum queues | Delivery counter in XPENDING | DeliveryCount property | `request.retries` (retries only) |

## Notes per broker

- SQS standard queues are at least once and unordered; FIFO queues add
  ordering per message group and a deduplication window, which complements but
  does not replace application idempotency.
- RabbitMQ quorum queues track delivery counts and support a delivery limit;
  classic queues need application-side counting.
- Redis Streams keep unacknowledged entries in a pending list; a reaper must
  reclaim entries from dead consumers, and retention trimming must not drop
  pending work.
- Service Bus locks expire unless renewed; it supports scheduled messages,
  sessions for ordered processing, and duplicate detection windows.
- Celery acknowledges early by default; set late acknowledgement and
  reject-on-worker-lost for at-least-once delivery, and size the transport
  visibility timeout above the longest task plus countdown for Redis and SQS.
  [celery_app.py.template](../assets/celery_app.py.template) applies these
  settings.

## Choosing

Prefer the queue your platform already operates well. Pick by the features
you need (delays, ordering, lock renewal, dead-lettering, delivery counts) and
by operational maturity, then implement the port once and run the same
contract tests against the adapter and the in-memory broker.

## Sources

- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html)
- [RabbitMQ quorum queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Azure Service Bus message sessions and scheduling](https://learn.microsoft.com/en-us/azure/service-bus-messaging/message-sequencing)
- [Celery configuration reference](https://docs.celeryq.dev/en/stable/userguide/configuration.html)
