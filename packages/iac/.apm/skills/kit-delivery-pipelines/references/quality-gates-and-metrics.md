# Quality gates and delivery metrics

Verified as of 2026-10-27 against the DORA metrics guide, the GitHub
deployments REST API, the GitHub status-check documentation, and the Google
SRE workbook.

## Order gates from cheap to expensive

Each gate should fail fast and cheaply before the next one spends time,
runners, or user exposure. A typical order:

| Order | Gate | Where | Owner of the detail |
| --- | --- | --- | --- |
| 1 | Format, lint, type check | pull request CI | repository tooling |
| 2 | Unit and component tests | pull request CI | the service |
| 3 | Dependency review and lock audit | pull request CI | `kit-supply-chain` |
| 4 | Workflow security scan (pins, permissions, untrusted input) | pull request CI | `kit-ci-review` |
| 5 | Build the artifact once; image scan; provenance attestation | trunk CI | `kit-containers`, `kit-supply-chain` |
| 6 | Integration and contract tests against the built artifact | trunk CI or dev | the service |
| 7 | Deploy to dev and test; smoke and synthetic checks | CD | this skill |
| 8 | Infrastructure plan or what-if review when infrastructure changes | CD, before apply | `kit-terraform-validation`, `kit-azure-validation` |
| 9 | Release readiness (versioning, changelog, notes) for published releases | release | `kit-release` |
| 10 | Approval, canary analysis, SLO burn-rate watch | production | this skill and `kit-observability` |

Rules for every gate:

- A gate either blocks or is informational; never a "warning" people learn to
  ignore. Informational gates live in a separate, clearly named job.
- Gates run against the same commit and artifact that will ship. Results from
  an earlier commit or a different build do not count.
- Flaky tests are defects in the gate: quarantine with an owner and a date,
  never retry until green.
- Required checks need stable job names, must run on `pull_request` and
  `merge_group`, and must not be skippable by path filters into a pending or
  success state (see `pipeline-architecture.md`).

## Test tiers by stage

| Tier | Runs | Scope | Budget |
| --- | --- | --- | --- |
| Unit and component | every pull request | in process, no network | minutes |
| Integration | trunk build or pull request with containers | real database, broker, or emulator | under about 15 minutes |
| Contract | pull request of producer and consumer | API and event schemas | minutes |
| Smoke | every deploy | a few critical endpoints of the deployed artifact | seconds |
| Synthetic journeys | after promotion and continuously | scripted user flows in production | continuous |
| Performance and resilience | scheduled or before risky releases | load, failure injection | hours, not per change |

Keep the pull request path under roughly ten minutes so people keep batches
small; move slower suites to the trunk build and fix forward quickly when they
fail.

## Post-deploy verification

- Smoke checks hit readiness plus one or two read paths through the public
  URL of the exact revision or slot (label URL, slot host name) before it
  takes traffic, and again through the production URL after promotion.
- Synthetic checks run on a schedule, independent of the pipeline, so a
  regression that appears after the bake window is still caught.
- The canary gate compares the candidate with the stable version (error ratio,
  latency percentiles, saturation) over the bake window; a single absolute
  threshold hides regressions in low-traffic periods.
- Every check emits a clear pass or fail into the job log and the step
  summary; dashboards are evidence, not gates.

## Delivery metrics (DORA)

DORA now describes five software delivery performance metrics, grouped as
throughput and instability:

| Metric | Group | Definition | Compute from |
| --- | --- | --- | --- |
| Change lead time | throughput | time from commit to running in production | commit timestamps of the commits first shipped by each successful production deployment |
| Deployment frequency | throughput | production deployments per period | successful production deployments |
| Failed deployment recovery time | throughput | time to recover from a deployment that needed immediate intervention | `restored_at` minus the deployment's completion time |
| Change fail rate | instability | share of deployments that needed immediate intervention (rollback, roll forward, hotfix) | deployments marked `caused_incident` |
| Deployment rework rate | instability | share of deployments that were unplanned and made because of a production incident | deployments marked `unplanned` |

The original four keys (deployment frequency, lead time for changes, time to
restore, change fail rate) remain the core. DORA reports also measure
operational performance (reliability) next to them, and the current guide
adds the rework rate. Pair the
delivery metrics with the service SLO from `kit-observability` so speed is
never read without reliability.

Pitfalls DORA calls out: turning metrics into targets (Goodhart's law), one
metric to rule them all, comparing unrelated applications, using industry as a
shield, siloed ownership, competing between teams, and spending more on
measurement than improvement. Measure one service at a time and use the
trend, not a league table.

### Measuring from GitHub deployments

Jobs that name an environment create deployment records automatically. The
REST API provides the raw data:

- `GET /repos/{owner}/{repo}/deployments?environment=production` returns
  deployments with `sha`, `ref`, `environment`, and `created_at`.
- `GET /repos/{owner}/{repo}/deployments/{id}/statuses` returns states
  (`queued`, `pending`, `in_progress`, `success`, `failure`, `error`,
  `inactive`). A later successful deployment marks earlier ones `inactive`.
  Previous statuses are kept for 90 days (the current status is kept on the
  deployment), so export on a schedule.
- Commit times come from comparing the deployed `sha` with the previous
  production `sha` (`GET /repos/{owner}/{repo}/compare/{base}...{head}`).
- Change failures and recovery times come from the incident process, not from
  GitHub: record `caused_incident`, `restored_at`, and `unplanned` when the
  incident is handled (see the runbook template).

The metrics template reads such an export and prints the five metrics for one
environment and window; it falls back to failed deployment statuses for the
change fail rate when no incident data exists and says so in the report.

```text
gh api --paginate "repos/OWNER/REPO/deployments?environment=production" > deployments-raw.json
python tools/dora_metrics.py deployments.json --environment production --since 2026-07-01 --until 2026-10-01
```

Transforming the raw API output into the record shape (one object per
deployment with final status, status time, and commit times) is a short
consumer-owned script; keep it with the export job so its assumptions are
reviewed.

## Review checklist

- [ ] Gates are ordered cheap to expensive and each blocks or is clearly
      informational.
- [ ] Required checks cannot be bypassed by path filters or skipped jobs.
- [ ] Smoke checks run against the candidate before traffic and against
      production after promotion.
- [ ] Canary analysis compares candidate and stable with written thresholds.
- [ ] Delivery metrics are computed per service from deployment records, with
      incident data for change failures, and read alongside the SLO.

## Sources

- <https://dora.dev/guides/dora-metrics/>
- <https://cloud.google.com/blog/products/devops-sre/announcing-dora-2021-accelerate-state-of-devops-report>
- <https://docs.github.com/en/rest/deployments/deployments>
- <https://docs.github.com/en/rest/deployments/statuses>
- <https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks>
- <https://sre.google/workbook/canarying-releases/>
- <https://dora.dev/capabilities/trunk-based-development/>
