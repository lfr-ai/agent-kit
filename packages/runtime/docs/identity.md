# Opt-in Entra identity

The base `create_app` remains health-only. Identity is enabled explicitly; neither
the base package nor `platform_kit_runtime.identity` imports optional SDKs merely
by being imported. Install the reviewed runtime `auth` extra through the owning
project's dependency workflow. This capability targets Entra v2, not arbitrary
OIDC providers; its ports permit future adapters without pretending they exist.

## Public composition

All consumer-facing symbols below are in `platform_kit_runtime.identity`.

- `IdentityConfig`: frozen, keyword-only, slotted configuration. Required:
  canonical UUID `tenant_id`, canonical UUID `client_id`, exact `api_audience`,
  and a fixed `origin` such as `https://app.example` (no trailing slash/path).
  Host case, IPv6 notation and default ports are normalized at construction:
  `https://APP.TEST:443` becomes `https://app.test`. Ambiguous encoded/numeric
  host aliases are rejected rather than producing unusable browser origins.
  Hosts are RFC 1123 names (letters, digits, hyphens, dots) or bracketed IPv6
  literals, and port 0 is rejected.
  Authority is always `https://login.microsoftonline.com/{tenant_id}`; redirect
  URI is always `{origin}/auth/callback`. Request/forwarded headers cannot
  change either. Invalid configuration raises a credential-free `ValueError`.
  Malformed UUID errors retain a fixed, value-free message without chaining raw
  parser diagnostics into the formatted exception traceback.
- `open_entra_identity(*, config, redis_url, assertion)`: async context manager,
  yielding `IdentityRuntime`; owns and closes HTTPX and Redis clients.
  `assertion` implements `ClientAssertion.__call__() -> str`, supplying a
  short-lived signed confidential-client assertion from consumer-owned
  federation/certificate configuration. No client secrets or environment
  discovery are built into this capability.
- `IdentityRuntime.install(*, app)`: before startup, conveniently installs both
  BFF routes and identity-only error handlers. For resource-backed routes
  installed inside lifespan, first call `install_identity_handlers(app=...)`
  **before startup**. Starlette snapshots handlers when it builds middleware,
  before entering lifespan. Late handler registration and lifespan installation
  with missing handlers raise an explicit `RuntimeError`, rather than silently
  serving identity errors as 500s. A raw `router()` also checks handler
  registration during startup. Install routes once; use a fresh app per lifespan.
- `open_entra_bearer(*, config)`: async context manager yielding a
  `BearerValidator`, with no MSAL or Redis import/resource requirement.
- `BearerGuard(*, config, validator, scopes, roles)`: callable FastAPI dependency
  returning a safe `Principal`. Supply both frozensets; at least one must be
  nonempty. Every supplied scope **and** role is required, not any-of.
- `SessionGuard(*, config, service)`: callable browser dependency returning a
  safe `Principal`; unsafe HTTP methods require CSRF and origin before refresh.
  Use `Principal.require(scopes=..., roles=...)` for browser authorization.
- `create_identity(*, config, store, provider, graph, validator)`: pure
  composition for caller-owned ports. No resource creation or network I/O.
  Ports: `IdentityStore`, `IdentityProvider`, `GraphReader`, `BearerValidator`.
  Safe records: `Principal`, `SafeProfile`, `Avatar`, `ImageType`.
  Server-only records: `ProviderLogin`, `ProviderTokens`; never serialize these
  or the application's internal sessions into a transport response.

Example BFF composition with the runtime factory's optional lifespan:

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.identity import (
    ClientAssertion,
    IdentityConfig,
    install_identity_handlers,
    open_entra_identity,
)


def build_app(
    *,
    identity_config: IdentityConfig,
    redis_url: str,
    assertion: ClientAssertion,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with open_entra_identity(
            config=identity_config,
            redis_url=redis_url,
            assertion=assertion,
        ) as identity:
            identity.install(app=app)
            yield

    app = create_app(config=RuntimeConfig(), probes=(), lifespan=lifespan)
    install_identity_handlers(app=app)
    return app
```

Compose any other application resource lifespans rather than overwriting them.
For API-only applications, install identity handlers before startup, enter
`open_entra_bearer` in the resource lifespan, and attach
`Depends(BearerGuard(...))` to consumer-owned protected routes.
No business or sample authenticated routes are installed by the runtime.
Creation/lifespan entry makes no network requests; dependency failures occur
when an operation first needs its upstream.

### Keyless confidential-client credentials

The runtime does **not** require a long-lived client secret. Pass the assertion
**supplier**, not its return value: MSAL receives
`client_credential={"client_assertion": supplier}` and invokes it only when
sending a token request, including refresh. Offline tests assert that the
authorization-code and refresh requests obtain separate assertions and never
contain a `client_secret` field.

For Azure public-cloud managed-identity federation, the consumer can use its
user-assigned managed identity to acquire
`credential.get_token("api://AzureADTokenExchange/.default").token` inside this
synchronous supplier. Configure the corresponding federated identity credential
on the Entra application separately. Other workload federation assertion
acquisition can implement the same callable. Acquisition failures must be
translated by the consumer to `DependencyUnavailableError`, chained from the
credential SDK exception; never put credential diagnostics in logs.

No `azure-identity` dependency is necessary for this runtime seam. Consumers
choosing that SDK to obtain managed-identity assertions own its dependency,
credential lifecycle and configuration. Assertions must be current; do not
capture one expiring assertion at startup. The supplier must be thread-safe
because MSAL calls it in worker threads. Provisioning app registrations,
federated credentials, consent and managed identities is outside this package.

## Browser contract

| Route | Behavior |
| --- | --- |
| `GET /auth/login?return_to=/path` | 303 to Entra; creates one-time login state |
| `GET /auth/callback?code=...&state=...` | Consumes state, validates proof, rotates session; 303 to safe return path |
| `POST /auth/logout` | Requires origin/CSRF; deletes local session, clears both cookies; 204 |
| `GET /auth/me` | Safe tenant/user identifiers, profile display name, CSRF proof |
| `GET /auth/avatar` | Bounded PNG/JPEG bytes, or 404 when no photo exists |

`/auth/me` returns only:

```json
{
  "identity": {"tenant_id": "<UUID>", "subject_id": "<UUID>"},
  "profile": {"display_name": "Display name or null"},
  "csrf_token": "<session-bound random proof>"
}
```

Send the CSRF proof in `X-CSRF-Token` and the exact configured `Origin` on
state-changing browser operations. Apply `SessionGuard` to consumer-owned
mutations. Missing, duplicated or mismatched proof fails closed. Logout is
local, not Entra single sign-out; it does not require a token refresh. Origin is
checked before reading session state. Read outages return 503 and clear browser
cookies only after origin validation; actual server-side deletion still requires
the session's CSRF proof.

Cookies are opaque, `Secure`, `HttpOnly`, `SameSite=Lax`, host-only, path `/`,
named `__Host-pk-login` and `__Host-pk-session`. State/nonce/PKCE are generated
and validated with MSAL; PKCE verifier and token caches remain in Redis.
Each callback consumes the browser-bound state even when proof is invalid.
An independent PyJWT signature/issuer/audience/tenant/time check validates
the ID token before accepting its identity. No access, refresh or ID token
is returned to the browser. Login codes necessarily appear in callback queries:
disable/redact query strings in deployment-owned access logs.

MSAL 1.39 emits a `UserWarning` recommending `form_post` for improved protection
against authorization-code leakage. This implementation preserves the approved
GET callback and code-only flow; SDK tests explicitly expect that advisory.
It is not suppressed in production. Deployments treating warnings as errors
must account for it. Switching to POST callbacks is a separate public-contract
decision, not an implicit change here.

Return destinations must be safe origin-relative paths. Absolute URLs,
network-path references, backslashes, controls and ambiguous nested encodings
are rejected. Callback errors use 400; no upstream error text is reflected.
Responses use `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
Avatars also use `X-Content-Type-Options: nosniff`; SVG/HTML are never supported.

HTTP development requires `allow_insecure_loopback=True` **and** an explicit
loopback origin (`localhost`, IPv4/IPv6 loopback). Only then are non-Secure
`pk-local-*` cookies used. HTTPS origins always keep Secure cookies. Redis
requires `rediss://` unless the same explicit development flag permits a
loopback `redis://` endpoint. Redis URL query overrides are rejected.

## API validation and failure contract

API authentication verifies RS256 signatures with tenant-specific HTTPS JWKS,
exact v2 issuer, configured audience, mandatory `exp`/`nbf`/`iat`, tenant and
user identifiers. Only the JOSE header is read before signature verification.
Unknown algorithms, unsigned tokens, invalid signatures, wrong trust claims
and expired/future tokens fail closed. Permissions never come from unverified
claims. Use distinct API and BFF registrations/audiences where appropriate.

| Public exception | Status / stable problem code |
| --- | --- |
| `InvalidCallbackError` | 400 / `invalid_callback` |
| `AuthenticationRequiredError` | 401 / `authentication_required`; `WWW-Authenticate: Bearer` |
| `PermissionDeniedError` | 403 / `permission_denied` |
| `AvatarMissingError` | 404 / `avatar_missing` |
| `UpstreamFailureError` | 502 / `identity_upstream_failure` |
| `DependencyUnavailableError` | 503 / `identity_unavailable` |

All derive from `IdentityError`. Responses follow RFC 9457 with a fresh UUID
instance. One structured boundary log contains status/code/instance, never
exception text, tracebacks, cookies, tokens, profile or request details.
Configure SDK/server/proxy logging and CORS separately: permissive credentialed
CORS or raw access/error logging can defeat the privacy boundary.

## State, cache and operational limits

Redis 6.2+ is required (`GETDEL`, `EVAL`). Protect it as credential storage:
private networking, TLS, least-privilege ACLs, encryption and retention policy.
All keys incorporate a hash of the full identity configuration. Different
tenants, registrations, audiences, origins, development modes or TTL policies
cannot consume each other's logins, authenticate/delete each other's sessions,
or share profile caches even when they share Redis. Configuration changes
therefore intentionally invalidate the previous namespace until its TTLs expire.
Login state expires after 300 seconds. Sessions default to an absolute 3600
seconds, configurable through `session_ttl_seconds` up to 86400. Refresh uses
one atomic comparison plus `SET XX EX`, never recreating a missing session.
A racing refresh fails closed if logout, expiry or another refresh won.
A failed Redis session read or deletion during valid-origin logout returns 503,
clears browser cookies, and does **not** claim confirmed revocation; any
still-stored credential expires by its TTL. Wrong/missing origins cannot use an
outage to clear cookies or trigger session reads.

Graph calls are server-only delegated `User.Read`, to `/v1.0/me` with only
`displayName` selected and `/v1.0/me/photo/$value`. Redis cache keys hash the
tenant **and** user; profile and photo never share keys. Missing photos are
cached. Cache TTL defaults to 300 seconds, bounded to 900; photos are limited
to 256 KiB with supported media type and byte-signature checks. JSON is bounded
to 64 KiB. Cached data may be stale until TTL. Cache misses coalesce within a
worker; simultaneous misses in different workers can each fetch Graph once.

JWKS are cached in-process for 300 seconds. Discovery attempts, including failed
ones, are limited to one every 30 seconds per worker/validator. During cooldown,
unknown keys or stale/missing caches fail closed with the recorded safe failure
category. Unexpired known keys still require normal signature/claim validation.
Failed discovery never extends the lifetime of cached keys.
HTTPX uses explicit 10-second I/O timeouts, bounded pools, no redirect following,
no environment proxies, and bounded/uncompressed bodies. MSAL's blocking work
runs in worker threads; request cancellation cannot terminate an already-running
SDK thread. Deploy appropriate request/concurrency limits and shutdown grace.

Offline regressions use ephemeral stores, actual MSAL/PyJWT with synthetic
signatures, mock HTTP transports and a Redis atomic-command model. The installed
wheel is tested outside the checkout with optional SDK imports forbidden.
Real atomic-server proof can use a native Redis process or a parent-provisioned
isolated Redis/Valkey server selected by `RUNTIME_REDIS_TEST_URL`. Only
credential-free loopback URLs are accepted; UUID-scoped keys receive targeted
cleanup and short TTLs. No database flush or container provisioning is performed.
The optional server test proves only the exercised atomic-store operations.
These checks do not certify hosted Entra/Graph integration or identity deployment.
Registration, consent, workload assertions, Redis operations,
production CORS and deployment/access logging remain operator-owned.

## Official references

- [MSAL Python API](https://learn.microsoft.com/en-us/python/api/msal/msal.application.confidentialclientapplication?view=msal-py-latest):
  confidential-client assertions, authorization-code flows and silent refresh.
  The [versioned MSAL 1.39 source](https://github.com/AzureAD/microsoft-authentication-library-for-python/blob/1.39.0/msal/application.py)
  documents the lazy, renewable callable-assertion contract.
- [Entra managed-identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-config-app-trust-managed-identity):
  keyless trust configuration and the token-exchange audience.
- [Entra access tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens):
  resource-specific audience, issuer, tenant and signature validation.
- [Graph user profile](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0)
  and [photo](https://learn.microsoft.com/en-us/graph/api/profilephoto-get?view=graph-rest-1.0).
- [PyJWT verification](https://pyjwt.readthedocs.io/en/stable/usage.html).
- Redis [GETDEL](https://redis.io/docs/latest/commands/getdel/) and
  [atomic scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/).
- [OAuth security BCP, response leakage](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.3.1).
