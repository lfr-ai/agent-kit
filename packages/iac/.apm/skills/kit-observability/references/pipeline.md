# Telemetry pipeline: collector, sampling, privacy, cost

## Collector topology

- Send telemetry from applications over OTLP to a local or nearby
  OpenTelemetry Collector (agent or sidecar), then to a gateway collector
  or the backend. Applications then need no backend credentials and can
  switch backends without code changes.
- Pipeline order matters: `memory_limiter` first, then filtering and
  scrubbing, then enrichment (`resource`), then `batch` last before
  exporters.
- Enable the exporter sending queue and retry so short backend outages do
  not drop data, and size the queue to the memory limit.
- Expose the `health_check` extension for orchestrator probes, and monitor
  the collector's own metrics (accepted, refused, dropped, queue size).
- Validate configuration with `otelcol validate --config <file>` (or the
  distribution's binary) in CI.

## Sampling

- Head sampling (`ParentBased(TraceIdRatioBased(r))`) decides at the root
  span; cheap and consistent across services because children follow the
  parent's decision.
- Tail sampling (collector `tail_sampling` processor) decides after the trace
  completes, so it can keep all errors and slow traces while sampling
  successful ones. It needs all spans of a trace on the same collector
  instance (load-balancing exporter by trace ID).
- Never sample metrics; they are already aggregated. Sample logs only by
  severity or with explicit rules.
- Record the sampling ratio so dashboards that count spans can scale them.

## Privacy and security

- Scrub at the source first (instrumentation and log formatters) and again
  in the collector (`attributes`, `transform`, or `redaction` processors).
- Delete credentials (authorization headers, cookies, API keys) and personal
  data (emails, names, addresses); hash identifiers only when correlation is
  required and the hash is not reversible by enumeration.
- Encrypt OTLP traffic between collectors and to the backend; authenticate
  exporters with platform identity rather than embedded keys.
- Define retention per signal and environment, and restrict who can query
  production telemetry.

## Cost and backpressure

- Drop noise before export: health-check spans, debug logs, unused metric
  attributes.
- Watch cardinality and log volume per service; alert on sudden growth.
- Instrumentation must never block the request path: SDK processors batch
  asynchronously and drop data when queues are full rather than slowing the
  application.

## Review checklist

- [ ] Applications export OTLP to a collector, not directly to a vendor.
- [ ] Collector pipelines start with `memory_limiter` and end with `batch`.
- [ ] Sampling strategy written down; errors are always retained.
- [ ] Credentials and personal data are removed in code and in the collector.
- [ ] Retention, access, and encryption are defined per environment.

Template: [collector configuration](../assets/templates/otel-collector.yaml.template).

## Sources

- <https://opentelemetry.io/docs/collector/>
- <https://opentelemetry.io/docs/collector/configuration/>
- <https://opentelemetry.io/docs/collector/deployment/>
- <https://opentelemetry.io/docs/concepts/sampling/>
- <https://opentelemetry.io/docs/security/handling-sensitive-data/>
- <https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/memorylimiterprocessor/README.md>
- <https://github.com/open-telemetry/opentelemetry-collector/blob/main/processor/batchprocessor/README.md>
