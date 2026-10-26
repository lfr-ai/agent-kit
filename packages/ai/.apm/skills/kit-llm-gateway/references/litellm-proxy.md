# LiteLLM proxy operation

Reviewed 2026-10-23 against the LiteLLM proxy documentation (latest release
observed: v1.106.2). Configuration keys change between releases; check the
pinned version's reference before relying on a key.

## Configuration sections

| Section | Owns | Notes |
| --- | --- | --- |
| `model_list` | Aliases (`model_name`) mapped to deployments (`litellm_params`) | Several entries with one alias form a load-balanced group |
| `router_settings` | Routing strategy, retries, timeout, cooldowns, fallbacks, Redis for shared state | Required for consistent limits across replicas |
| `litellm_settings` | Module settings: callbacks, cache, request timeout, parameter dropping, key bounds | `turn_off_message_logging` keeps content out of callbacks |
| `general_settings` | Master key, database, health checks, database overlay | `store_model_in_db: false` keeps the file authoritative |
| `environment_variables` | Values injected into the process | Do not put secrets here; use the deployment's secret store |

Any value can be an `os.environ/NAME` reference. Use it for every key,
password, database URL and endpoint that differs per environment.
With `store_model_in_db` enabled, database rows overlay the file for the
settings sections, so a file edit may not change the running value; keep it
disabled unless the admin UI is the deliberate source of truth.

## Aliases and routing

- Name aliases for the job (`chat-default`, `extract-strict`, `embed-default`);
  clients send aliases only. Map an alias to pinned provider snapshots.
- Put deployments with identical models and data terms under one alias and
  set `rpm` and `tpm` per deployment so the router can weigh them.

| Strategy | Use when | Caveat |
| --- | --- | --- |
| `simple-shuffle` (default) | Most cases; weighted by `rpm`/`tpm` when set | Not latency-aware |
| `least-busy` | Long-running requests with uneven duration | Needs shared state across replicas |
| `usage-based-routing` | Hard per-deployment quotas | Extra Redis traffic |
| `latency-based-routing` | Latency-sensitive interactive traffic | Can concentrate load on one region |

## Retries, timeouts, cooldowns and fallbacks

- Pick one retry layer. When the proxy retries (`router_settings.num_retries`),
  clients and the `kit-llm-client` policy wrapper do not retry the same call.
- Set a per-deployment `timeout` (and `stream_timeout` for streams) plus a
  global `router_settings.timeout` or `litellm_settings.request_timeout`.
- `allowed_fails` and `cooldown_time` take a failing deployment out of
  rotation; keep cooldowns enabled in production.
- `fallbacks` cover rate limits and outages; `context_window_fallbacks` cover
  oversized prompts. Fall back only to aliases that passed the same
  evaluation suite and share residency and contractual terms.
- Avoid `content_policy_fallbacks` to another provider: a refusal is a
  product outcome, not an outage.
- Validate fallbacks by inducing a real provider error in a non-production
  environment; per-request mock flags are not honored by recent proxy releases.

## Virtual keys, budgets and rate limits

- Virtual keys require `general_settings.master_key` and a database. Keep the
  master key for administration only; services use their own virtual keys.
- Create keys per service and environment with `/key/generate`: allowed
  `models`, `max_budget`, `budget_duration`, `rpm_limit`, `tpm_limit` and
  expiry. Group services into teams with team budgets when several share a
  quota.
- Cap what any key may request with
  `litellm_settings.upperbound_key_generate_params`.
- Budgets are enforced on recorded spend, which depends on accurate pricing
  data for each model; reconcile against provider invoices.
- Rotate virtual keys like any credential; revoke on service retirement.

## Caching

- Exact-match response caching (`cache: true`, `cache_params.type: redis`)
  helps repeated deterministic calls such as embeddings and classification.
- Set a TTL; caching changes evaluation results and can serve one user's
  output to another for identical prompts. Scope or disable it for
  personalized or sensitive requests.
- Semantic caching trades correctness for hit rate; evaluate it like a model
  change before enabling it.

## Observability with Langfuse

- `success_callback` and `failure_callback` with `langfuse` send traces;
  credentials come from `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
  `LANGFUSE_HOST` in the environment.
- Set `turn_off_message_logging: true` unless content capture was approved;
  metadata, tokens, cost and latency still arrive.
- Set `redact_user_api_key_info: true` so key hashes and user ids stay out
  of traces.
- Forward the application's trace and request ids as request metadata so
  gateway spans join the application trace.

## Health and operation

- Orchestrators probe `/health/liveliness` and `/health/readiness`; neither
  calls a model.
- `/health` calls every model and costs tokens; prefer
  `background_health_checks` with an interval and `health_check_details:
  false` when the endpoint is broadly reachable.
- Pin the image by tag and digest; read release notes for changed defaults
  before upgrading, and run the gateway evaluation suite after.
- The proxy is another network service: keep it on a private network, put
  TLS in front, and restrict the admin UI.
- License: the repository mixes an MIT-licensed core with separately licensed
  enterprise features; confirm which features a deployment uses.

## Primary sources

- [Proxy configuration](https://docs.litellm.ai/docs/proxy/configs)
- [All settings reference](https://docs.litellm.ai/docs/proxy/config_settings)
- [Fallbacks, retries, timeouts and cooldowns](https://docs.litellm.ai/docs/proxy/reliability)
- [Virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys)
- [Budgets and rate limits](https://docs.litellm.ai/docs/proxy/users)
- [Caching](https://docs.litellm.ai/docs/proxy/caching)
- [Langfuse logging](https://docs.litellm.ai/docs/proxy/logging)
- [Health checks](https://docs.litellm.ai/docs/proxy/health)
- [Production checklist](https://docs.litellm.ai/docs/proxy/prod)
