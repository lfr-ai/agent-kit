# Observability and operations

Background work fails quietly. Every queue needs metrics that reveal backlog
and failure before users notice, and runbooks that make recovery routine.

## Metrics

| Metric | Why | Typical alert |
| --- | --- | --- |
| Queue depth (visible and in flight) | Backlog size | Sustained growth over a window |
| Age of the oldest message | User-visible delay; better than depth | Above the task's freshness target |
| Throughput (completed per minute) per task type | Capacity | Drop to zero while depth is non-zero |
| Outcomes per task type (acked, duplicate, deferred, retried, dead-lettered, lease lost) | Health and duplicate rate | Dead-lettered above zero; lease lost rising |
| Attempts per completed task | Hidden retry cost | Mean attempts rising |
| Handler duration percentiles | Lease and timeout tuning | p99 approaching the lease |
| Dead-letter depth and arrivals | Unprocessed work | Any arrival for critical task types |
| Worker concurrency in use and restarts | Saturation and crashes | Restarts in a short window |

The template worker logs one structured record per outcome
(`task.outcome`, `task.dead_lettered`) with task type, task id, correlation
id, attempt and outcome, and never payload content. Export the same
dimensions as metrics labels; avoid high-cardinality labels such as task ids.

## Tracing and correlation

- Carry a correlation or trace id in the envelope (`correlation_id`) from the
  request that enqueued the task, and continue the trace in the worker.
- Record the enqueue time so end-to-end latency (enqueue to completion) is
  measurable, not only handler time.

## Runbooks

Write one per queue, covering:

1. Backlog growing: check worker health and dependency latency; scale workers
   only if the bottleneck is worker capacity, not a dependency.
2. Dead letters arriving: read reasons, fix, then follow the replay procedure
   in [retries-and-dead-letter.md](retries-and-dead-letter.md).
3. Duplicate side effects reported: confirm idempotency keys are business
   derived and that downstream calls pass them.
4. Lease lost rising: compare handler duration to the lease; check renewal.
5. Incompatible versions dead-lettered after a deploy: roll workers forward or
   back so they accept the produced versions; replay.

## Operator tooling

- Inspect a message by id without exposing payload secrets.
- Redrive selected dead letters in batches with an audit record.
- Pause a task type (stop consuming) without stopping the whole worker fleet.
- Purge is destructive; require confirmation and record who did it.

## Testing operations

The template tests cover duplicate delivery, crash and redelivery after lease
expiry, lease renewal for long tasks, lost leases, exhausted retries,
permanent failures, malformed and incompatible messages, redrive, and
shutdown. Add a load test that measures oldest-message age under a realistic
burst before launch.

## Sources

- [OpenTelemetry semantic conventions for messaging](https://opentelemetry.io/docs/specs/semconv/messaging/)
- [Amazon SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [RabbitMQ monitoring](https://www.rabbitmq.com/docs/monitoring)
- [Celery monitoring and management](https://docs.celeryq.dev/en/stable/userguide/monitoring.html)
