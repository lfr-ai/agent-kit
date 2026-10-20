# Signals and semantic conventions

## Three signals, one context

| Signal | Answers | Shape |
| --- | --- | --- |
| Traces | Where did this request spend time, and where did it fail? | Spans with parent/child links across services |
| Metrics | How much, how fast, how often, across all requests? | Pre-aggregated time series |
| Logs | What exactly happened at this point? | Timestamped structured records |

Connect them: logs carry `trace_id` and `span_id`; metrics can carry
exemplars that point to traces; all three share the same resource attributes.

## Resource attributes

Every signal from a process carries the same resource:

- `service.name` (required; stable logical name, not the host name)
- `service.version` (deployed build or release)
- `deployment.environment.name` (`dev`, `prod`; set centrally in the
  collector when possible)
- `service.instance.id` where instances must be told apart

Set them with `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` or in code.
A missing `service.name` produces `unknown_service` and breaks every
dashboard query.

## Semantic conventions

Use the OpenTelemetry semantic conventions instead of inventing names, so
backends, dashboards, and auto-instrumentation agree. Current stable HTTP
names include:

| Attribute or metric | Example |
| --- | --- |
| `http.request.method` | `GET` (unknown methods become `_OTHER`) |
| `http.route` | `/orders/{id}` (template, never the raw path) |
| `http.response.status_code` | `503` |
| `url.path`, `url.scheme`, `server.address`, `server.port` | Span attributes only; avoid on metrics |
| `error.type` | Exception class or status code when the operation failed |
| `http.server.request.duration` | Histogram in seconds |
| `db.system.name`, `db.operation.name`, `db.collection.name` | Database spans |

Pin the semantic convention version you follow, and migrate deliberately:
older instrumentation emits `http.method` and `http.status_code`, and the
`OTEL_SEMCONV_STABILITY_OPT_IN` variable controls dual emission during
migration in many instrumentation libraries.

## Traces

- Name spans by operation with low cardinality (`GET /orders/{id}`,
  `orders.process`), never with IDs.
- Propagate context with W3C Trace Context (`traceparent`, `tracestate`)
  across HTTP, messaging, and background jobs. For queues, inject context
  into message headers and link consumer spans to producer spans.
- Mark failures with span status `ERROR` and `record_exception`; do not set
  status `OK` on success unless the instrumentation convention requires it.
- Do not put secrets, tokens, or personal data into attributes or events.
  `baggage` propagates to every downstream service, including third parties.

## Structured logs

- Emit one JSON object per line with `timestamp` (UTC, ISO 8601), `severity`,
  `message`, `logger`, and `trace_id`/`span_id` when inside a span.
- Put variable data in fields, not in the message string, so messages group
  and fields can be redacted.
- Redact at the source: remove authorization headers, cookies, passwords,
  tokens, and personal data before the record leaves the process.
- Log an exception once, at the boundary that handles it, with its type and
  stack trace; do not log and rethrow at every layer.
- Choose severities consistently: ERROR for failed operations needing
  attention, WARNING for degraded but handled, INFO for lifecycle events,
  DEBUG off in production by default.

## Review checklist

- [ ] Resource attributes set; `service.name` stable.
- [ ] Attribute and metric names follow a pinned semantic convention version.
- [ ] Context propagates across every process and queue boundary.
- [ ] Logs are structured JSON with trace correlation and source redaction.
- [ ] No secrets or personal data in attributes, events, baggage, or logs.

Template: [Python instrumentation](../assets/templates/telemetry.py.template).

## Sources

- <https://opentelemetry.io/docs/concepts/signals/>
- <https://opentelemetry.io/docs/concepts/resources/>
- <https://opentelemetry.io/docs/specs/semconv/>
- <https://opentelemetry.io/docs/specs/semconv/http/http-spans/>
- <https://opentelemetry.io/docs/specs/semconv/http/http-metrics/>
- <https://opentelemetry.io/docs/concepts/context-propagation/>
- <https://opentelemetry.io/docs/specs/otel/logs/>
- <https://opentelemetry.io/docs/languages/sdk-configuration/general/>
- <https://www.w3.org/TR/trace-context/>
