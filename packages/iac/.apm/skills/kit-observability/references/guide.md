# Observability review guide: gates, failure modes, and recovery

## Reference map

| Concern | Reference |
| --- | --- |
| Traces, metrics, logs, resource attributes, semantic conventions, structured logging | [Signals and conventions](signals-and-conventions.md) |
| RED and USE, instrument choice, histogram buckets, cardinality | [Metrics design](metrics-design.md) |
| SLIs, SLOs, error budgets, burn-rate alerts, alert hygiene | [SLOs and alerts](slos-and-alerts.md) |
| Collector pipelines, sampling, privacy, cost | [Pipeline](pipeline.md) |
| Liveness, readiness, startup probes; metric naming; dashboards as code | [Probes and naming](probes-and-naming.md) |

## Quality gates

- Each signal answers a written operational question with a named owner.
- Instrumentation uses OpenTelemetry (or the repository standard) with
  `service.name`, `service.version`, and `deployment.environment.name`.
- Names follow a pinned semantic convention version.
- Metric attributes come from bounded sets; per-event identifiers live on
  spans and logs only.
- Logs are structured JSON with trace correlation and redaction at source.
- Context propagates across every service and queue boundary.
- User-facing services have SLOs and multi-window burn-rate alerts with
  runbooks; a missing-telemetry alert exists.
- Collector pipelines are memory-limited, batched, scrubbed, and validated.

## Failure modes

- A user ID or raw URL as a metric attribute multiplies series until the
  backend throttles or the bill spikes.
- Logs include authorization headers or personal data.
- A queue consumer starts a new trace, so producer and consumer cannot be
  joined.
- Alerts fire on every brief error spike and are muted; real incidents are
  missed.
- The telemetry pipeline breaks silently and dashboards show a flat, healthy
  line.
- Instrumentation blocks requests when the exporter is slow.

## Negative cases

- `counter.add(1, {"user.id": user_id})`.
- `logger.info(f"login for {email} with token {token}")`.
- Span names containing order IDs.
- Static threshold page on "error rate above 1% for 1 minute".
- Collector pipeline without `memory_limiter`.

## Recovery

1. Replace unbounded attributes with bounded buckets or move them to spans;
   drop the offending attributes in a collector view or processor meanwhile.
2. Add redaction in the formatter and the collector; purge affected data per
   the retention and incident policy.
3. Inject and extract trace context at the boundary that lost it.
4. Replace threshold pages with burn-rate alerts on SLIs.
5. Add an `absent_over_time` alert and collector self-monitoring.

## Prerequisites

- Instrumentation source or synthetic telemetry samples (never production
  data without owner approval).
- Collector configuration, sampling, and retention settings.
- The SLO document and alert rules, if they exist.

## Templates

- [Collector configuration](../assets/templates/otel-collector.yaml.template)
- [Collector local override](../assets/templates/otel-collector.local.yaml.template)
- [Python instrumentation](../assets/templates/telemetry.py.template)
- [Alert rules](../assets/templates/alert-rules.yaml.template)
- [RED and USE rules](../assets/templates/red-use-rules.yaml.template)
- [Grafana dashboard](../assets/templates/grafana-dashboard.json.template)
- [Grafana data source](../assets/templates/grafana-datasources.yaml.template)
- [Grafana dashboard provider](../assets/templates/grafana-dashboards.yaml.template)
- [Prometheus configuration](../assets/templates/prometheus.yaml.template)
- [Local observability stack](../assets/templates/observability-compose.yaml.template)
- [Telemetry evidence record](../assets/templates/telemetry-evidence-template.md)

## Sources

- <https://opentelemetry.io/docs/>
- <https://opentelemetry.io/docs/collector/configuration/>
- <https://prometheus.io/docs/guides/opentelemetry/>
- <https://sre.google/workbook/alerting-on-slos/>
