# Metrics design: RED, USE, instruments, and cardinality

## What to measure

- RED for request-driven services, per route and operation:
  Rate (requests per second), Errors (failed requests per second or ratio),
  Duration (latency distribution).
- USE for resources (CPU, memory, connection pools, queues, disks):
  Utilization (busy fraction), Saturation (queued work), Errors.
- Business throughput metrics (orders accepted, invoices issued) answer
  whether the system is doing its job even when technical metrics look fine.

A single latency histogram with a status attribute provides all three RED
signals: its count gives rate, filtering by status gives errors, and buckets
give duration percentiles.

## Instrument choice

| Instrument | Use for | Example |
| --- | --- | --- |
| Counter | Monotonic totals | Requests handled, bytes sent |
| UpDownCounter | Values that rise and fall, recorded as deltas | Active connections, queue depth |
| Histogram | Distributions | Request duration, payload size |
| Gauge (observable) | Sampled current values | Memory in use, pool size |

- Record durations in seconds with unit `s`; sizes in bytes with unit `By`.
- Choose histogram buckets around the SLO threshold (for example many
  buckets between 50 ms and 1 s for a 300 ms target) with views; consider
  exponential histograms where the backend supports them.
- Never compute percentiles in the application and export them as gauges;
  percentiles cannot be aggregated across instances.

## Cardinality

Every unique combination of attribute values is a separate time series.
Cost, memory, and query latency grow with that product.

- Attribute values must come from a small, bounded set: route templates,
  methods, status codes, outcome enums, region, tenant tier.
- Never use user IDs, emails, order IDs, session IDs, full URLs, raw paths,
  query strings, exception messages, or timestamps as metric attributes.
  Put them on spans or logs, where per-event detail belongs.
- Budget cardinality per metric (for example under 1,000 series per service
  instance) and alert on series growth.
- Map unknown values to a sentinel (`_OTHER`) instead of passing them through.
- Use views to drop attributes that instrumentation libraries add but you do
  not query.

## Exemplars

Exemplars attach a trace ID to individual histogram measurements so a latency
spike on a dashboard links directly to an example trace. Enable them where
the backend supports them; they add no series.

## Review checklist

- [ ] Every request path has RED coverage; every critical resource has USE.
- [ ] Instruments match semantics; units are SI base units.
- [ ] Histogram buckets resolve the SLO threshold.
- [ ] No unbounded attribute values on metrics.
- [ ] Cardinality budget documented and monitored.

## Sources

- <https://opentelemetry.io/docs/concepts/signals/metrics/>
- <https://opentelemetry.io/docs/specs/otel/metrics/supplementary-guidelines/>
- <https://opentelemetry.io/docs/specs/otel/metrics/data-model/>
- <https://opentelemetry.io/docs/languages/python/instrumentation/#metrics>
- <https://prometheus.io/docs/practices/naming/>
- <https://prometheus.io/docs/practices/histograms/>
- <https://prometheus.io/docs/practices/instrumentation/>
