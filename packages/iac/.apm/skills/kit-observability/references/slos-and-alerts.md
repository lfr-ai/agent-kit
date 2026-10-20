# SLOs and alerting

## Define the objective first

- A service level indicator (SLI) is a ratio of good events to valid events,
  measured as close to the user as practical: successful requests over all
  requests, or requests faster than a threshold over all requests.
- A service level objective (SLO) sets a target for the SLI over a window,
  for example 99.9% of requests succeed over 30 days.
- The error budget is `1 - SLO` (0.1% here). It is the amount of failure the
  team accepts; spending it fast is what deserves a page.
- Exclude invalid events explicitly (health checks, client errors that are
  the caller's fault) and document the exclusion.

## Burn-rate alerts

Burn rate is the observed error ratio divided by the error budget. A burn
rate of 1 consumes exactly the budget over the SLO window; 14.4 consumes 2%
of a 30-day budget per hour.

Alert on two windows at once: a long window proves the burn is significant,
and a short window proves it is still happening, so alerts reset quickly.

| Severity | Long window | Short window | Burn rate | Budget consumed when it fires |
| --- | --- | --- | --- | --- |
| Page | 1 h | 5 min | 14.4 | 2% |
| Page | 6 h | 30 min | 6 | 5% |
| Ticket | 1 day | 2 h | 3 | 10% |

Burn-rate alerts replace static thresholds such as "error rate above 1%",
which page on brief blips and miss slow erosion.

## Alert hygiene

- Every alert has an owner, a severity that maps to a response (page means
  act now; ticket means act this week), and a `runbook_url`.
- Alert on symptoms users feel (errors, latency, freshness), not on every
  cause (CPU spikes). Use cause metrics on dashboards and in runbooks.
- Include an alert for missing telemetry (`absent_over_time`) so a broken
  pipeline is not mistaken for a healthy service.
- Use `for:` to require persistence, and route by labels rather than by alert
  names.
- Unit-test alert rules with `promtool test rules` using synthetic series,
  and review alert volume monthly; delete alerts nobody acts on.

## Review checklist

- [ ] Each user-facing service has written SLIs, SLOs, and an error budget.
- [ ] Paging alerts are multi-window burn-rate alerts on SLIs.
- [ ] Every alert has an owner, severity, and runbook link.
- [ ] Missing-telemetry alert exists.
- [ ] Rules pass `promtool check rules` and have unit tests.

Template: [alert rules](../assets/templates/alert-rules.yaml.template).

## Sources

- <https://sre.google/sre-book/service-level-objectives/>
- <https://sre.google/workbook/alerting-on-slos/>
- <https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/>
- <https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/>
- <https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/>
- <https://prometheus.io/docs/practices/alerting/>
