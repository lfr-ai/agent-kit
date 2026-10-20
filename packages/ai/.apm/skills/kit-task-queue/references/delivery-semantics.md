# Delivery semantics and idempotency

## What brokers actually promise

| Guarantee | Meaning | How it fails |
| --- | --- | --- |
| At most once | Acknowledge before processing | A crash loses the task |
| At least once | Acknowledge after processing | A crash, timeout, or lost acknowledgement runs the task again |
| Exactly once (claimed) | Broker deduplicates within a window, or a transaction spans consume and produce inside one system | Side effects outside that system still run more than once |

Design for at least once. Assume every task can run twice, concurrently or
minutes apart, and make the result the same as running it once. Do not rely
on a broker's exactly-once feature unless the whole path, including every
external side effect, is inside its transactional boundary.

## Idempotency keys

- Derive the key from the business operation, not from the message id:
  `invoice.render:INV-42:v3`, not a random task id. A re-submitted request then
  produces the same key ([task_contracts.py.template](../assets/task_contracts.py.template)
  keeps `task_id` and `idempotency_key` separate for this reason).
- Include the version of the input in the key when a newer input must be
  processed again (`document.index:DOC-7:<source_version>`).
- Pass the key to downstream systems that accept idempotency keys, so the side
  effect itself deduplicates.

## Where deduplication happens

| Technique | Strength | Cost |
| --- | --- | --- |
| Idempotency store claim and complete (template worker) | Skips completed work; blocks concurrent duplicates | A crash between side effect and `complete` re-runs the side effect |
| Natural idempotence (upsert by key, set state, compare-and-set) | Re-running is harmless by construction | Needs a data model that supports it |
| Inbox table in the same transaction as the side effect | Exactly-once effect for database side effects | Side effect must be in the same database |
| Downstream idempotency key | Exactly-once effect at the external system | External system must support it and retain keys long enough |

Combine them: the store avoids wasted work, and natural idempotence or an
inbox makes the remaining re-runs harmless.

## Order of operations in the worker

1. Claim the key. `DONE` means acknowledge without work; `IN_PROGRESS` means
   another worker holds it, so retry later.
2. Run the handler.
3. Mark the key done.
4. Acknowledge the message.

A crash after step 3 and before step 4 causes a redelivery that is
acknowledged without work. Acknowledging before marking done would let a
separate duplicate submission run again.

## Producing tasks reliably

Enqueueing after a database commit can lose tasks (crash between commit and
enqueue); enqueueing before the commit can publish tasks for data that never
committed. Use a transactional outbox: write the task to an outbox table in
the same transaction as the business change, and let a relay publish outbox
rows and mark them sent. The relay itself is at least once, so the idempotency
key protects consumers.

## Ordering

Most queues do not guarantee order across consumers, and retries reorder
tasks. If order matters, make handlers commutative (apply only newer versions
by comparing a version or timestamp), or use a partitioned queue with one
consumer per key and accept the throughput limit.

## Payloads

- Keep payloads small: references and versions, not documents. Fetch data at
  processing time, and handle "not found" as a permanent failure or a no-op.
- Never put secrets or credentials in payloads; the envelope rejects common
  secret field names, and the queue validator reports them.
- Version payload schemas per task type; deploy workers that accept the new
  version before producers emit it, and keep accepting the old version until
  the queue drains.

## Sources

- [Amazon SQS: at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html)
- [Amazon SQS FIFO: exactly-once processing](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [RabbitMQ: reliability guide](https://www.rabbitmq.com/docs/reliability)
- [Azure Service Bus: duplicate detection](https://learn.microsoft.com/en-us/azure/service-bus-messaging/duplicate-detection)
- [AWS Prescriptive Guidance: transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Celery: tasks and acks_late](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
