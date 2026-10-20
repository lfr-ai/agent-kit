---
name: kit-observability
description: Use when reviewing metrics, traces, and logs to ensure they answer operational questions while protecting privacy and scale.
license: MIT
---

# Review observability

Telemetry is useful only when it answers operational questions, stays
affordable, and leaks nothing. Start with the [review guide](references/guide.md).

## Procedure

1. Write the operational questions the change must answer (is it up, is it
   fast, is it correct, where did this request fail) and map each to a
   signal and an owner.
2. Confirm instrumentation uses OpenTelemetry or the repository standard,
   sets `service.name`, `service.version`, and `deployment.environment.name`,
   and follows a pinned semantic convention version
   ([signals and conventions](references/signals-and-conventions.md)).
3. Check RED coverage for every request path and USE coverage for critical
   resources; verify instrument types, SI units, and histogram buckets around
   the SLO threshold ([metrics design](references/metrics-design.md)).
4. List every metric attribute and its value source. Reject values from
   unbounded input (user, order, or session IDs, raw paths, emails, messages)
   and require sentinel mapping for unknown values.
5. Check structured logging: JSON records, trace correlation, variable data
   in fields, one log per handled exception, and redaction at the source.
6. Trace context across every boundary: inbound and outbound HTTP, queues,
   scheduled jobs. Confirm no secrets or personal data in attributes, events,
   or baggage.
7. Review the pipeline with [pipeline](references/pipeline.md): OTLP to a
   collector, `memory_limiter` first and `batch` last, exporter queue and
   retry, scrubbing processors, documented sampling that keeps errors, and
   retention and access per environment.
8. Review SLOs and alerts with [SLOs and alerts](references/slos-and-alerts.md):
   SLIs as good/valid ratios, multi-window burn-rate pages, owners, runbooks,
   a missing-telemetry alert, and `promtool` checks and tests.
9. Emit representative synthetic telemetry locally (console or debug
   exporter) and confirm names, attributes, and series counts. Never scan
   production data without owner approval.
10. When proposing configuration, adapt the
    [collector](assets/templates/otel-collector.yaml.template),
    [Python instrumentation](assets/templates/telemetry.py.template), and
    [alert rules](assets/templates/alert-rules.yaml.template) templates.
11. Record results in the
    [telemetry evidence record](assets/templates/telemetry-evidence-template.md):
    samples, sampling, retention, risky attributes, and owners of each fix.

## Acceptance gates

- [ ] Every operational question maps to a signal and owner.
- [ ] Resource attributes and semantic conventions are correct.
- [ ] No unbounded metric attributes; cardinality budget stated.
- [ ] Logs are structured, correlated, and redacted at the source.
- [ ] Context propagates across all boundaries.
- [ ] Collector config validated; memory-limited, scrubbed, batched.
- [ ] SLO burn-rate alerts with runbooks and a missing-telemetry alert.
- [ ] Synthetic samples and evidence record attached.

## Out of scope

Instrumentation completeness does not replace runbook drills or alert
testing in the operating environment.
