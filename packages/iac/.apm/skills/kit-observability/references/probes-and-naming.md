# Probes, metric naming, and cardinality

Reviewed 2026-10-23.

## Health, readiness, and startup probes

| Probe | Question | On failure | Must check | Must not check |
| --- | --- | --- | --- | --- |
| Startup | Has the process finished initializing? | Keep waiting, then restart after the budget | Initialization done (migrations checked, caches warmed) | Anything slow that runs after startup |
| Liveness | Is the process stuck beyond recovery? | Restart the container | Event loop or worker responsiveness | Databases, downstream APIs, disk space |
| Readiness | Should this instance receive traffic now? | Remove from load balancing, no restart | Dependencies this instance needs to serve requests, drain state | Optional dependencies with fallbacks |

- Liveness that checks a shared dependency restarts every replica during a
  dependency outage and turns a partial failure into a full one.
- Readiness turns false at the start of shutdown, before connections drain,
  so load balancers stop sending traffic first.
- Use a startup probe for slow starters instead of a long liveness delay.
- Keep probes cheap, unauthenticated on a private port or path, exempt from
  rate limits, and excluded from traces and access logs (the collector
  template drops `/healthz` and `/readyz` spans).
- Return a status code only; never expose versions, hostnames, or
  dependency error text on a probe endpoint.
- Probe timeouts and thresholds: interval times failure threshold is the
  detection delay; make it shorter than the platform grace period.

Conventional paths: `/healthz` (liveness), `/readyz` (readiness),
`/startupz` or the readiness path with a startup budget.

## Metric naming

| Rule | Example |
| --- | --- |
| Use OpenTelemetry semantic convention names when one exists | `http.server.request.duration` |
| Base units, stated once | Seconds (`s`), bytes (`By`); never milliseconds in the name |
| Prometheus exposition adds unit and type suffixes | `http_server_request_duration_seconds_bucket`, `_total` for counters |
| Namespace custom metrics by domain | `orders.checkout.duration`, not `duration` |
| Name what is measured, not the aggregation | `queue.depth`, not `avg_queue_depth` |
| Recording rules use `level:metric:operations` | `job_route:http_server_requests:rate5m` |
| Never encode label values in the name | `http_requests{method="GET"}`, not `http_get_requests` |

Prometheus 3 translates OTLP names with unit and type suffixes by default;
check the names in your backend before writing rules and dashboards.

## Cardinality

Each unique label combination is a separate time series. Estimate before
adding a label: series = product of distinct values per label.

| Label | Distinct values | Verdict |
| --- | --- | --- |
| `http_route` (template) | Tens | Keep |
| `http_response_status_code` | About 20 | Keep |
| Raw URL path or query | Unbounded | Reject; use the route template |
| User, session, order, or trace ID | Unbounded | Reject; put on spans and logs |
| Pod or instance ID | Grows with every deploy | Keep only where needed; aggregate in recording rules |

- Budget series per service and alert on growth
  (`count by (__name__) ({job="orders-api"})` over time).
- Drop unused attributes in SDK views or collector processors.
- Promote only a few resource attributes to labels; leave the rest in
  `target_info` and join when needed.
- Detailed rules live in [metrics design](metrics-design.md).

## Dashboards as code

- Provision dashboards and data sources from files; disable UI edits for
  provisioned dashboards so version control stays the source.
- Select data sources with a `datasource` template variable; never commit
  instance-specific data source UIDs from an exported dashboard.
- Leave the dashboard `id` null and avoid exported UIDs; set a stable,
  human-chosen `uid` only when another dashboard or alert links to it.
- Base panels on recording rules so dashboards and alerts agree.

## Primary sources

- <https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/>
- <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>
- <https://learn.microsoft.com/azure/container-apps/health-probes>
- <https://prometheus.io/docs/practices/naming/>
- <https://prometheus.io/docs/practices/rules/>
- <https://prometheus.io/docs/guides/opentelemetry/>
- <https://opentelemetry.io/docs/specs/semconv/general/metrics/>
- <https://grafana.com/docs/grafana/latest/administration/provisioning/>
- <https://grafana.com/docs/grafana/latest/dashboards/variables/add-template-variables/#add-a-data-source-variable>
