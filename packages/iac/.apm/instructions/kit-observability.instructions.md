---
description: Apply to metrics, OpenTelemetry, tracing, and logging configuration.
applyTo: "**/observability/**,**/monitoring/**,**/*otel*,**/*prometheus*,**/*grafana*"
---

- Follow OpenTelemetry semantic conventions for span, metric, and attribute names where one exists.
- Use low-cardinality dimensions; never put user ids, request ids, or free text in metric labels.
- Keep personal identifiers, secrets, prompts, and full request or response payloads out of logs, spans, and metrics.
- Keep logs structured with a level, event name, and trace or correlation id; log actionable events, not every step.
- Bound buffers, batch sizes, sampling, export retries, and retention so telemetry cannot exhaust the service.
- Never let telemetry failure fail the request path; export asynchronously and drop data under overload.
- Propagate trace context only across defined boundaries and preserve error semantics; record exceptions on spans and set error status.
- Avoid duplicate instrumentation at multiple layers for the same operation.
- Alert on symptoms users feel (errors, latency, saturation) with a runbook link, not on every metric.
- Keep dashboards and alert rules in version control with the service.
- Configure exporters and endpoints through environment configuration, not code constants.
- Test emitted data with synthetic values and keep production export checks separate.
- Use the `kit-observability` skill for instrumentation procedures.
