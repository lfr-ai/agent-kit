# API Management policies

Verified as of 2026-10 against the sources listed at the end. Policy names,
attributes, and tier support change; check each policy's reference page for
your tier before relying on it. Templates:
[global](../assets/policies/global.xml.template),
[API](../assets/policies/api.xml.template), and
[model API](../assets/policies/ai-api.xml.template). Gate them with
[check_apim_policy.py](../assets/check_apim_policy.py).

## Scopes, sections, and `<base />`

Scopes, outermost first: global, workspace, product, API, operation. Each
policy document has four sections:

| Section | Runs | Typical content |
| --- | --- | --- |
| `inbound` | Before the request is forwarded | CORS, authentication, limits, validation, backend selection, header changes |
| `backend` | Around the call to the backend | `forward-request` timeout, retry |
| `outbound` | After the response arrives | Header clean-up, response validation, cache store, metrics |
| `on-error` | When any step raises an error | Status mapping, problem body, error logging |

- `<base />` marks where the enclosing scope's policies run. Leave it out and
  those policies silently stop applying for this scope: a global rate limit,
  header scrub, or error renderer disappears without any error. Every section
  below global scope keeps exactly one `<base />`.
- Place `<base />` first in `inbound` and `outbound` unless a policy must run
  before inherited ones. In `on-error`, put scope-specific status mapping
  first and `<base />` last so a single global handler renders the body.
- Global scope has no parent and therefore no `<base />`.
- Policy fragments (`include-fragment`) hold shared XML; give each fragment an
  owner and treat it like code, because every API that includes it changes
  when it changes.
- Element and attribute order inside each policy follows its reference page;
  the gateway rejects some out-of-order children.

## Expressions and well-formed XML

- Expressions are C# in `@(...)` (single expression) or `@{...}` (statement
  block). The policy document is still XML: escape `&` as `&amp;` and `<` as
  `&lt;` inside attributes, or rewrite the expression (`!(x >= 400)` instead of
  `x < 400`).
- When an expression contains double quotes, wrap the attribute in single
  quotes. The templates follow this so they parse with any XML parser.
- Keep expressions short. A block longer than a few lines belongs in the
  service, not in gateway configuration that is hard to test.

## Authentication at the gateway

- `validate-jwt` checks a JWT from a header, query parameter, or value. Give
  it the issuer's OpenID configuration URL (signing keys are fetched and cached
  from it), explicit `audiences`, explicit `issuers`, `require-scheme="Bearer"`,
  required claims for coarse scopes, and a short `clock-skew`. Keep
  `require-signed-tokens` and `require-expiration-time` at `true`.
- `validate-azure-ad-token` is the Entra-specific variant (tenant, client
  application IDs, audiences). Use it when every caller is an Entra
  application.
- `validate-client-certificate` checks a client certificate's thumbprint,
  issuer, subject, or validity; combine it with the instance's client
  certificate setting.
- Use `output-token-variable-name` to reuse validated claims (for example the
  subject as a rate-limit key) instead of parsing the header again.
- The gateway check is coarse. The service still validates the token and
  authorizes every object (`kit-auth`); see
  [security and operations](security-and-operations.md).
- Remove `Authorization` and `Ocp-Apim-Subscription-Key` before forwarding
  when the service receives its own gateway-issued identity
  (`authentication-managed-identity`); forward the caller token only when the
  service must see the user's identity, and then never log it.

## Rate limits and quotas

| | Rate limit | Quota |
| --- | --- | --- |
| Purpose | Protect capacity from spikes | Enforce a plan allowance |
| Window | Short; `renewal-period` up to 300 seconds | Long; minimum 300 seconds, often a month, or lifetime |
| Over-limit response | `429 Too Many Requests` with `Retry-After` | `403 Forbidden` with `Retry-After` |
| Per subscription | `rate-limit` | `quota` |
| Per arbitrary key | `rate-limit-by-key` | `quota-by-key` |
| Tokens of model APIs | `llm-token-limit` `tokens-per-minute` | `llm-token-limit` `token-quota` + `token-quota-period` |

Rules that come from the reference pages:

- Counters are approximate. The rate-limit page states that distributed
  throttling is never completely accurate; actual counts vary with volume,
  latency, and other factors.
- Counters are kept per gateway: regional gateways in a multi-region
  deployment, workspace gateways, and self-hosted gateways count separately
  and do not aggregate across the instance. A self-hosted gateway can
  synchronize counts among its own replicas only.
- One counter exists per `counter-key` value across every scope that uses
  it. Prefix keys with the scope (`orders:`, `orders-quota:`) unless sharing is
  intended. On v2 tiers (token bucket) keep the limit value identical wherever
  the same key appears.
- `increment-condition` with an expression moves counting to the end of the
  outbound pipeline, so the 429 arrives one call late.
- The `-by-key` variants are not available in the Consumption tier. The
  `quota-by-key` page header lists classic tiers while the gateway table lists
  v2; confirm on your tier before relying on it.

Choosing keys:

- Key on who the consumer is: subscription ID, or a validated token claim
  (`sub`, client ID). Never key on a header the caller can set freely.
- `context.Request.IpAddress` is the address of the previous hop. Behind Front
  Door, Application Gateway, or another proxy, it is the proxy; use an IP key
  only for a coarse backstop or on a header that only the trusted edge sets.
- Expose remaining calls and `Retry-After` so well-behaved clients back off.
- Business limits that depend on application state (for example "three
  password resets per hour per account") stay in the service and its shared
  counter store (`kit-fastapi-service`).

## Caching

- `cache-lookup` (inbound) and `cache-store` (outbound) cache whole GET
  responses. The built-in cache is volatile and shared by all units in a
  region; an external Redis-compatible cache survives gateway restarts and is
  the only option in the Consumption tier.
- Cache only public, non-personalized responses unless every personalizing
  input is a vary-by key. Requests with an `Authorization` header are not cached
  unless `allow-private-response-caching` is set; if you set it, vary by
  `Authorization` too.
- Add `vary-by-header` for `Accept` and `Accept-Charset` and any header that
  changes the representation, and `vary-by-query-parameter` for each relevant
  parameter.
- Put a rate limit after the cache lookup so a cache outage does not
  overwhelm the backend.
- The service still owns its HTTP caching semantics (`Cache-Control`, `ETag`,
  `Vary`); the gateway cache must not contradict them. Application caching is
  `kit-caching`; CDN and proxy caches are `kit-edge-networking`.

## Headers and CORS

- `set-header` with `exists-action` `override`, `skip`, `append`, or `delete`.
  Delete server and framework banners in outbound; delete inbound credentials
  that the service must not see.
- `cors` answers preflight requests at the gateway. List exact origins; with
  `allow-credentials="true"` a wildcard is invalid and with any setting it is
  a policy smell. Keep `terminate-unmatched-request="true"` so unmatched
  preflight requests end at the gateway. Configure CORS in one place: the gateway or
  the service, not both with different lists.
- Correlation: keep a caller's `X-Correlation-Id` (or W3C `traceparent`) and
  otherwise use `context.RequestId`; echo it in responses and error bodies so
  support can find the gateway log entry.

## Validation against the contract

- `validate-parameters` checks path, query, and header parameters against the
  imported API description; `validate-content` checks body size and JSON or
  XML schema; `validate-headers` and `validate-status-code` check responses.
- Actions are `ignore`, `detect` (log only), or `prevent` (reject). Roll out
  with `detect` and `errors-variable-name`, read the logged violations, then
  switch to `prevent`.
- `validate-content` checks `max-size` against `Content-Length` (decompressed
  length for compressed bodies), up to 4 MB; schemas used by validation are
  limited to 4 MB.
- These checks are only as good as the imported OpenAPI document. Re-import it
  from the contract owner's file on every change (`kit-api-contracts`).

## Backend selection and resilience

- `set-backend-service backend-id="..."` routes to a backend entity that owns
  the URL, TLS validation, credentials, and the circuit breaker; see
  [concepts](apim-concepts.md).
- `forward-request timeout` (seconds) bounds the backend call. Order timeouts
  so the innermost hop gives up first: service < gateway < edge < client.
- `retry` can repeat the forward for idempotent operations only, with a small
  count and interval. Prefer the circuit breaker plus client retries with
  jitter over gateway retries that multiply load during an incident.

## AI gateway policies

Names verified on the policy reference at the check date. The policy index
lists only the `llm-*` names, and the `azure-openai-token-limit` reference
page now redirects to `llm-token-limit`; older `azure-openai-*` names still
appear in some articles. Use the `llm-*` policies for new configuration.

- `llm-token-limit`: per-key token rate (`tokens-per-minute`) and/or quota
  (`token-quota`, `token-quota-period` hourly to yearly). Over the rate limit
  the caller gets 429; over the quota, 403. With `estimate-prompt-tokens`
  `false`, counting uses the usage section of the response, so a request can
  still reach the model after the limit is crossed; streaming requests always
  estimate. Concurrent requests can briefly overshoot. Counters are per
  gateway. Not in the Consumption tier.
- `llm-emit-token-metric`: sends prompt, completion, and total token counts
  to Application Insights with up to five custom dimensions. Each dimension is
  limited to 100 distinct values and each namespace to 1,000 active time
  series; extra series are dropped silently, so never use user IDs or request
  IDs as dimensions. Some providers need `include_usage` for streaming counts.
- `llm-semantic-cache-lookup` / `llm-semantic-cache-store`: cache by vector
  similarity using an external cache and an embeddings backend. Similar is not
  equal: the reference warns that it can return incorrect, outdated, or unsafe
  responses. Partition with `vary-by` (at least the subscription) and enable
  only after evaluation.
- `llm-content-safety`: sends prompts to Azure AI Content Safety before the
  model call.
- Model selection, prompts, fallbacks across providers, and evaluation are
  `kit-llm-gateway` concerns; the API gateway only governs access and spend.

## Errors

- Without an `on-error` section callers receive default 400 or 500 responses.
  Define one global handler that renders `application/problem+json` (RFC 9457)
  with `type`, `title`, `status`, `instance`, and a correlation ID.
- `context.LastError` exposes `Source`, `Reason`, `Message`, `Scope`,
  `Section`, `Path`, and `PolicyId`. Map on `Source` and `Reason` (for example
  `validate-jwt`, `RateLimitExceeded`, `QuotaExceeded`, `Timeout`,
  `BackendConnectionFailure`) at API scope with `set-status`, then call
  `<base />`.
- `return-response` without `set-status` answers 200; always set the status.
- Never copy `context.LastError.Message`, stack traces, backend bodies, or
  token contents into responses. Log them, if at all, to a restricted sink.
- Application errors pass through unchanged; the service owns their problem
  documents (`kit-api-contracts`).

## Logging without leaking secrets

- Diagnostics settings log headers and bodies only when explicitly listed.
  Keep body bytes at 0 and header lists empty, or list only harmless headers;
  use data masking for query parameters such as `code` or `sig`.
- `trace` and `log-to-eventhub` write whatever you give them; never include
  `Authorization`, subscription keys, cookies, or named values that hold
  secrets.
- Secrets live in Key Vault-backed named values. A literal key, token, or
  password in XML is a defect even in a non-production file, because policy
  files are versioned and copied.

## Sources

- Policies overview and scopes:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-policies>
- Policy reference index:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-policies>
- Policy expressions:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-policy-expressions>
- validate-jwt: <https://learn.microsoft.com/en-us/azure/api-management/validate-jwt-policy>
- validate-azure-ad-token:
  <https://learn.microsoft.com/en-us/azure/api-management/validate-azure-ad-token-policy>
- rate-limit-by-key:
  <https://learn.microsoft.com/en-us/azure/api-management/rate-limit-by-key-policy>
- quota-by-key: <https://learn.microsoft.com/en-us/azure/api-management/quota-by-key-policy>
- Advanced request throttling:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-sample-flexible-throttling>
- cache-lookup: <https://learn.microsoft.com/en-us/azure/api-management/cache-lookup-policy>
- External cache:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-cache-external>
- cors: <https://learn.microsoft.com/en-us/azure/api-management/cors-policy>
- validate-content:
  <https://learn.microsoft.com/en-us/azure/api-management/validate-content-policy>
- validate-parameters:
  <https://learn.microsoft.com/en-us/azure/api-management/validate-parameters-policy>
- llm-token-limit:
  <https://learn.microsoft.com/en-us/azure/api-management/llm-token-limit-policy>
- llm-emit-token-metric:
  <https://learn.microsoft.com/en-us/azure/api-management/llm-emit-token-metric-policy>
- llm-semantic-cache-lookup:
  <https://learn.microsoft.com/en-us/azure/api-management/llm-semantic-cache-lookup-policy>
- Error handling:
  <https://learn.microsoft.com/en-us/azure/api-management/api-management-error-handling-policies>
- Problem Details for HTTP APIs (RFC 9457):
  <https://www.rfc-editor.org/rfc/rfc9457>
