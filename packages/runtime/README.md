# Platform Kit Runtime

`platform-kit-runtime` is a typed, MIT-licensed Python 3.13+ FastAPI/Starlette
foundation: health routes, explicit configuration, pluggable readiness, and
sanitized RFC 9457 errors. Its base installation includes no business routes,
authentication, provider integrations, or ASGI server.

Optional [Entra identity](docs/identity.md) adds an explicitly composed browser BFF
or API bearer guard; the base factory remains health-only.
Optional [text inference](docs/ai.md) loads LiteLLM only when the AI extra is
installed and selected.

## Keyless Azure v1 text inference and embeddings

The AI extra also supplies Azure Identity and its async HTTP transport, imported
only when the generated app explicitly selects managed identity authentication.
Key-based LiteLLM providers remain supported without loading Azure Identity.

Use `TextGenerationConfig(entra_authentication=True, model="openai/<deployment>",
api_base="https://<resource>.openai.azure.com/openai/v1/")` and
`create_text_generator(config=..., token_provider=...)`. The provider implements
`AsyncTokenProvider`: an async callable returning a current bearer token.
The caller owns it and its credential, including shutdown and failed-startup cleanup.
The adapter awaits the provider on every generation, within the same total
deadline as inference. It neither caches tokens nor starts renewal tasks.
Token acquisition failures/invalid tokens become sanitized `AIAuthenticationError`;
timeouts become `AIUnavailableError`, and cancellation propagates unchanged.
The existing application boundary logs each handled failure once, without tokens.
Inference remains text-only and non-streaming.

Generated apps require explicit `APP_ENVIRONMENT`: `local`, `dev`, `test`,
`staging`, or `prod`. There is no inferred/default stage. For keyless AI set:

```dotenv
APP_AI_ENTRA_AUTHENTICATION=true
APP_AI_MANAGED_IDENTITY_CLIENT_ID=<user-assigned-identity-client-uuid>
APP_AI_MODEL=openai/<deployment>
APP_AI_API_BASE=https://<resource>.openai.azure.com/openai/v1/
```

Remove `APP_AI_API_KEY` entirely, including empty values; omit
`APP_AI_API_VERSION`. The app lifespan creates an explicit async
`ManagedIdentityCredential(client_id=...)`, uses Azure's renewable
`get_bearer_token_provider` with scope `https://ai.azure.com/.default`, and closes
the credential. It never uses a default credential chain or Azure CLI login.
The documented `https://<resource>.services.ai.azure.com/openai/v1/` endpoint is
also supported. The adapter sends the deployment name to `/openai/v1/chat/completions`
using bearer authentication, not the legacy Azure deployment/version route.
SDK retries reuse that generation's token within the bounded inference deadline.

Retrieval embeddings use the same keyless mode:
`EmbeddingConfig(entra_authentication=True, model="openai/<deployment>",
api_base="https://<resource>.openai.azure.com/openai/v1/")` with
`create_litellm_embedder(config=..., token_provider=...)`. The token is
requested once per embedding batch, within that call's deadline, and sent to
`/openai/v1/embeddings` as a bearer token, so a Foundry resource can keep
`disableLocalAuth=true`. Key-based embeddings remain supported; see
[Retrieval](docs/retrieval.md#embedding-authentication).

Contract sources, reviewed 2026-11-13:
[Microsoft v1 endpoint and scope](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle?view=foundry-classic),
[LiteLLM OpenAI-compatible routing](https://docs.litellm.ai/docs/providers/openai_compatible),
[async Azure token provider](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.aio?view=azure-python#azure-identity-aio-get-bearer-token-provider).
Offline transport and lifecycle tests are not live Azure certification.

## Redis Entra limitation

Keyless Redis is **not implemented**. On 2026-11-13 the latest stable versions
were `redis==8.1.0` and `redis-entraid==1.2.2`.
The [official provider](https://github.com/redis/redis-py-entraid/blob/v1.2.2/redis_entraid/cred_provider.py)
delegates async renewal to Redis but exposes no public cleanup method or factory
option to disable recurring renewal safely.
Redis's [async renewal implementation](https://github.com/redis/redis-py/blob/v8.1.0/redis/auth/token_manager.py#L347)
does not retain its recurring timer for
[`stop()`](https://github.com/redis/redis-py/blob/v8.1.0/redis/auth/token_manager.py#L208).
An isolated offline experiment called public `start_async`, recorded its scheduled
timer, called `stop()`, and failed the assertion that the timer was cancelled:
`Official async token renewal remains scheduled after stop()`.
The experiment is retained in absolute session scratch, not the product test suite,
because this dependency feature has not been adopted. No production guard was
skipped or weakened. There is no custom refresh loop or private-API workaround;
do not wire the proposed Redis Entra settings until a reviewed public lifecycle
supports shutdown. Existing key-based/local Redis behavior is unchanged.

## Other opt-in features

Other opt-in features are composed explicitly and load their SDKs only when
their facade is imported:

| Feature | Facade | Extra | Guide |
| --- | --- | --- | --- |
| Request ID, access log and rate limit middleware | `platform_kit_runtime.middleware` | `ratelimit` for Redis counters | [HTTP middleware](docs/http-middleware.md) |
| OpenTelemetry server and inference traces over OTLP (Langfuse, Azure Monitor) | `platform_kit_runtime.telemetry` | `telemetry` | [Telemetry](docs/telemetry.md) |
| PostgreSQL engine, sessions and readiness | `platform_kit_runtime.database` | `database` | [Database](docs/database.md) |
| Chunking, embeddings, Azure AI Search and evaluation | `platform_kit_runtime.retrieval` | `retrieval` (plus `ai` for embeddings) | [Retrieval](docs/retrieval.md) |
| Document Intelligence text extraction | `platform_kit_runtime.documents` | `ocr` | [OCR](docs/ocr.md) |

## Creation API

```python
from fastapi import FastAPI

from platform_kit_runtime import RuntimeConfig, create_app


def build_app() -> FastAPI:
    return create_app(
        config=RuntimeConfig(),
        probes=(),  # Explicitly declare that this app has no dependencies.
    )
```

`create_app(*, config, probes, lifespan=None)` returns a new `FastAPI` instance.
`config: RuntimeConfig` and `probes: tuple[ReadinessProbe, ...]` are required and
keyword-only. The optional `lifespan` accepts FastAPI's native async context
manager for consumer-owned startup and teardown, without a second app factory.
Creation performs no I/O, calls no probes, and creates no ambient singleton.
`RuntimeConfig(*, readiness_timeout_seconds=2.0)` is frozen and slotted.
Its timeout must be a finite number in `(0, 60]` seconds; booleans are rejected.
Invalid values raise `ValueError` naming the field without echoing the value.
Configuration is explicit: no environment, dotenv, or file discovery.

## Readiness probes

The exported `ReadinessProbe` protocol requires `async def check(self) -> bool`.
Return `True` when ready or `False` when unavailable. Translate known availability
failures to the exported `ProbeUnavailableError`, using
`raise ProbeUnavailableError(...) from error`. Unexpected exceptions and
non-boolean results produce a generic 500, not a successful fallback.

Probes run concurrently on every readiness request, under one total deadline.
Timeouts and unexpected failures cancel and await unfinished work; request
cancellation propagates. Use non-blocking, cancellation-cooperative asyncio I/O
and make probes safe for concurrent requests. Blocking code or suppressed
cancellation cannot be bounded reliably.

Consumers own adapters, resource creation, lifespan, and teardown. The runtime
creates no clients, pools, retries, caches, or background workers.
Pass resource ownership through `lifespan`; startup failures prevent the app
from serving and propagate to the server. Install exception handlers before
startup, not inside the lifespan, because ASGI middleware is already constructed
when startup begins.

## HTTP contract

| Request/outcome | Status | Body / `code` |
| --- | --- | --- |
| `GET /health/live` | 200 | `{"status":"ok"}`; never calls probes |
| `GET /health/ready`, all ready (including explicit empty tuple) | 200 | `{"status":"ready"}` |
| Readiness false, expected unavailable, or timeout | 503 | Problem / `not_ready` |
| Unexpected exception or invalid probe result | 500 | Problem / `internal_error` |
| Unknown route | 404 | Problem / `not_found` |
| Unsupported method | 405 | Problem / `method_not_allowed`; safe `Allow` header |
| FastAPI request validation failure | 422 | Problem / `invalid_request` |
| 401 exception with missing, malformed, or unsupported challenge | 500 | Problem / `http_error` |
| Other standard HTTP error exception | Original 4xx/5xx | Problem / `http_error` |
| Over an opt-in `RuntimeConfig(rate_limit=...)` quota | 429 | Problem / `rate_limited`; `Retry-After` |

Nonstandard HTTP exception statuses and statuses below 400 become 500 with
`http_error`. Successful bodies use `application/json`. Errors use
`application/problem+json`. Runtime responses set `Cache-Control: no-store`.
Interactive documentation, OpenAPI HTTP routes, debug mode, and automatic
slash redirects are disabled. The factory adds only the two health routes.

Each problem contains `type: "about:blank"`, the standard HTTP `title`, matching
numeric `status`, generic `detail`, stable `code`, and a fresh UUID URN
`instance`. Clients should branch on status/code, not prose. Probe names and
dependency topology are not exposed.

Exception header lookup is case-insensitive. Validated method names in `Allow`
survive on 405. On 401, a single recognized Basic/Bearer challenge, optionally
with syntactically valid token/quoted parameters, is replaced with the fixed,
protocol-valid `Basic realm="runtime"` or `Bearer`. Bare Basic is repaired with
that fixed realm. Supplied realms, scopes, errors, descriptions, URLs, and tokens
are never echoed. This intentionally does not preserve consumer realm or scope
semantics; applications needing those own their reviewed error boundary.
Missing, malformed, unsupported, control-containing, or duplicate challenge
headers produce a sanitized 500 rather than a challenge-less 401.

## Database

`platform-kit-runtime[database]` adds an opt-in async PostgreSQL foundation on
SQLAlchemy and asyncpg; see [the database guide](docs/database.md).
`create_database(settings=..., credential=None)` opens no connection and returns
a `Database` with the engine, a `sessions` factory, a `session` FastAPI
dependency yielding one uncommitted session per request, a `probe` for
`create_app(probes=...)`, and a `lifespan` that disposes the pool. Wrap writes
in `transaction`.

`DatabaseSettings` is explicit: no connection URL, `PG*` variables or password
files. TLS with certificate and host-name verification is on by default.
`entra_authentication=True` uses a caller-owned async Azure credential to fetch
a short-lived token for each new pooled connection and recycles connections
before tokens expire. Invalid settings raise `DatabaseConfigurationError`
naming the field, never its value. Models, repositories and Alembic migrations
belong to the application; the declarative `Base` is provided for them.

## Privacy and operational limits

Each handled error emits one stdlib log record with `event`, `http_status`,
`problem_code`, `instance`, and a safe `failure_reason` when applicable.
No exception text, cause, traceback, request data, or validation details appear
in runtime logs or problem bodies.

Starlette re-raises unexpected exceptions after sending the 500 response; test
that response with `ASGITransport(raise_app_exceptions=False)`. Configure
deployment-owned server/access/error logs separately to prevent data leakage.
Do not enable debug mode or replace handlers while relying on this contract.
Streaming and background-task failures after response start, WebSockets,
server startup, and shutdown are outside this HTTP foundation.

## Dependencies and development

Runtime requirements are `fastapi>=0.162.0,<1` and `starlette>=1.10.0,<2`.
Optional extras are `auth`, `ai`, `telemetry`, `database`, `retrieval`, `ocr`
and `ratelimit`; the Azure-backed `database`, `retrieval` and `ocr` extras also
install the `aiohttp` transport their asynchronous clients need.
[pyproject.toml](pyproject.toml) defines build/test dependencies. The distribution
includes `py.typed` and has no dependency on Agent Kit tooling or checkout files.
Core and application orchestration use only the standard library; shared
endpoint, range and timeout checks live in `core/validation.py`, and limits
shared across features (request deadline, SDK retry cap, time units) have one
owner in `core/limits.py`.

Internal identity modules are grouped within their owning layers:

- `core/identity/`: models and validation, private state encoding, and ports.
- `application/identity.py`: browser/session use cases over those ports.
- `infrastructure/identity/`: Entra, Graph, HTTP and Redis adapters; shared
  upstream-status translation belongs here, not to the Graph adapter.
- `presentation/identity/`: request guards, BFF routes and sanitized problems.

Consumer imports remain the public facades: `platform_kit_runtime`,
`.identity`, `.ai`, `.middleware`, `.telemetry`, `.database`, `.retrieval` and
`.documents`. Internal module paths are not compatibility APIs.
`infrastructure/litellm.py` remains a single adapter module; no one-file
feature package is needed. Infrastructure and presentation never import each
other; neither core nor application imports SDKs or frameworks.

From the repository root, with the audited workspace environment installed:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/runtime tests/integration/runtime
task verify -- architecture
```

The integration suite builds a wheel offline with the root-pinned, cached
Hatchling toolchain, installs only that wheel into a temporary target, and checks
imports and health responses outside the checkout. The build cache must already
be provisioned; the test downloads no packages and does not change the workspace
environment.

For a no-installer artifact check, set `RUNTIME_TEST_WHEEL` to an already-built
local wheel and run
`tests/integration/runtime/test_identity_package.py::test_extracted_wheel_without_installer`.
It extracts the pure-Python wheel into a temporary directory, retains the
existing isolated metadata/health/facade assertions, imports every relocated
adapter, and enters the BFF lifespan with network connections blocked.
This checks the wheel's installed layout without exercising an installer or
altering the workspace environment. The two original installer-based tests
remain available for workflows that permit installation.
