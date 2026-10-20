# Retries, backoff, and dead-letter handling

## Classify every failure

| Failure | Class | Worker action |
| --- | --- | --- |
| Timeout, connection error, throttling, dependency 5xx | Retryable | Retry with backoff until the attempt limit |
| Unknown exception | Retryable (logged with type) | Same; investigate if it recurs |
| Validation error, missing entity, business rule violation | Permanent | Dead-letter immediately |
| Malformed body, unknown task type or version | Permanent | Dead-letter immediately |
| Duplicate already completed | Not a failure | Acknowledge without work |
| Duplicate in progress elsewhere | Not a failure | Retry later without counting as a handler failure |

Handlers raise `RetryableTaskError` or `PermanentTaskError`
([task_contracts.py.template](../assets/task_contracts.py.template)); the
worker ([worker.py.template](../assets/worker.py.template)) maps everything
else to retryable. Translate dependency errors at the adapter boundary so
handlers do not inspect SDK exception types.

## Backoff with jitter

Delay before attempt `n + 1` is a uniform random value in
`[0, min(max_delay, base * 2^(n-1))]` (full jitter). Exponential growth gives a
struggling dependency room to recover; jitter prevents thousands of tasks from
retrying in lockstep. Brokers implement the delay as a message delay or a
visibility extension (`Broker.retry(delay_s=...)`).

Choose the attempt limit from the business deadline: the sum of the maximum
delays plus handler timeouts must fit before the result becomes useless. A
report due in an hour does not need two days of retries.

## Dead-letter queues

A dead-letter queue parks messages that cannot be processed, so they stop
consuming worker capacity and are preserved for diagnosis and replay.

- Configure it on every queue; never discard failed messages silently.
- Record a safe reason (error type and category, never payload content) and
  the delivery count with each dead letter.
- Alert on dead-letter arrivals per task type, not only on dead-letter depth;
  a slow trickle is easy to miss.
- Keep dead letters at least as long as the incident response window, and
  apply the same data retention rules as the source queue.

## Poison messages

A poison message fails every time, usually because of data or a deployed bug.
Without an attempt limit it loops forever; with a limit it lands in the
dead-letter queue after a bounded cost. Watch for messages whose handler
crashes the worker process (out of memory, native crash): late acknowledgement
plus redelivery can then take down every worker in turn. Count deliveries
before running the handler and dead-letter at the limit even if the previous
attempt never reported a failure.

## Replay (redrive)

Replay is an operator action with a procedure:

1. Identify the cause from the dead-letter reason and logs.
2. Fix the code, data, or dependency; deploy.
3. Validate the parked messages (for example with
   [verify_queue_messages.py](../assets/verify_queue_messages.py)) against the
   versions the deployed workers support.
4. Redrive in small batches and watch error rates; idempotency keys make
   replay of already-completed work harmless.
5. Record what was replayed and why.

The in-memory broker's `redrive` and its test show the expected behavior;
managed queues provide redrive tooling with the same semantics.

## Sources

- [AWS Architecture Blog: exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [RabbitMQ dead letter exchanges](https://www.rabbitmq.com/docs/dlx)
- [Azure Service Bus dead-letter queues](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Celery: automatic retry for known exceptions](https://docs.celeryq.dev/en/stable/userguide/tasks.html#automatic-retry-for-known-exceptions)
