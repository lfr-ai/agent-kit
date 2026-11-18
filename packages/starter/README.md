# Starter foundation

The root [Copier configuration](../../copier.yml) renders APM onboarding and an
optional executable FastAPI service. It installs nothing, starts nothing,
queries no cloud account and does not initialize or publish a repository.

Copier is development-only tooling. Its GPL `jinja2-ansible-filters`
dependency is accepted under a dated, scope-tested [license
decision](../../docs/dependency-security.md#copier-development-tool); generated
projects never depend on it.

## Choices

- `kind`: library, backend, frontend or fullstack development guidance.
- `ai` and `identity`: existing APM guidance flags, not executable features.
- `service`: `none` (default) or `api` for backend/fullstack.
- API-only `data`: `none` (default) or `postgresql`.
- API-only `cache`: `none` (default) or `redis` shared rate limiting.
  Azure Redis with cloud IaC is blocked pending a supported Entra renewal/shutdown
  lifecycle; local Redis with `iac=none` is unchanged. No key fallback is supplied.
- API-only `auth`: `none` (default) or `entra-bearer`.
- API-only `ai_service`: `none` (default) or internal `text` generation.
- API-with-IaC `telemetry`: `none` (default) or `application-insights` for
  managed-identity-authenticated traces. Console diagnostics and platform
  alerts do not depend on this choice.
- `iac`: `none` (default), `bicep` or `terraform`; no IaC means no deployment
  scaffold. Selected IaC with the API adds dev/test/staging/prod parameter files
  and deployment templates; rendering itself never creates resources. An approved
  deployment provisions only selected PostgreSQL/text-AI services.
- API-with-IaC `registry`: `acr` (default; a private per-environment Azure
  Container Registry, OIDC push and managed-identity pull) or `ghcr` (public
  GHCR image; dev/evaluation only).
- API-only `ci`: `github` (default) or `azure-devops` (Azure Pipelines that
  extend the pinned delivery templates; requires `registry=acr` with IaC). Only
  the selected system's files are emitted.
- `kit_commit`: empty for capability-only adoption; an API requires an explicit,
  reviewed 40-character lowercase hexadecimal commit, excluding all-zero values.
- `agent_provider`: Copilot, Claude or both.

Executable AI/identity choices also select their corresponding APM guidance.
No automatic HEAD discovery occurs: a dirty checkout is not a reviewed release.
No credentials, alert destinations or provider secrets belong in Copier answers.

```powershell
uv run --locked --no-sync copier copy --defaults --data project_name=my-app --data kind=backend --data service=api --data kit_commit=<reviewed-published-40-character-sha> . <empty-destination>
```

The reviewed commit must be published and contain `packages/runtime`; the
runtime's uv Git source uses `rev`, not an unpublished tag or mutable branch.
APM profiles separately retain their reviewed release coordinates. Nothing in
offline generation proves that those remote artifacts are available.

## Fast local path

The default API needs Python 3.13+, uv 0.12/0.13, Git and Task, but no Azure
account, Azure CLI login, Docker or APM installation:

```sh
cp .env.example .env
task local:setup
task start
```

In PowerShell, use `Copy-Item .env.example .env`. Review the file first and never
overwrite existing configuration. Selected services need their required
settings and local dependencies before startup.

The first task resolves/audits/installs the application environment. Review and
commit `uv.lock`; startup uses the existing lock without syncing.
Agent capability installation remains the separate `task setup` workflow.
`task verify` checks APM ownership plus application checks; use
`task test -- tests/test_health.py -k live` for focused application feedback.
With no selector, pytest discovers only the application tests, not installed
capabilities. Ruff and pytest configuration remain in dedicated files.

The generated application has health routes, safe error responses and explicit
stdlib structured logging with correlation filtering. Raw access URLs, headers,
bodies and exception text are not serialized; Uvicorn raw access logging is off.
Errors retain logger/module/function/line, exception class and bounded traceback
frame identifiers, without filenames, source lines or locals. Configuration
failures report declared field names and cause class, with no exception context.
There is no frontend, business logic, migration or seed data.

## Opt-in executable services

Settings live in `src/app/settings.py`: process environment overrides local
`.env`, which overrides defaults. `.env.example` documents local settings;
`.env.dev.example`, `.env.test.example`, `.env.staging.example` and
`.env.prod.example` document the same selected features for every cloud stage,
including when IaC is not selected. Copy exactly one example to `.env`; stage
files are never auto-loaded or merged. Real `.env` and `.env.*` files are
git-ignored, while secret-free examples remain tracked. Remote examples keep TLS
enabled and require operator-supplied endpoints and credentials/identities.
Missing or invalid required configuration fails without credential values.
Disabled features install/import no optional service libraries.

- PostgreSQL composes the runtime database factory, readiness probe and disposal
  lifespan. The database is on `app.state.database` for session injection.
  Password authentication remains the local default. Explicit
  `APP_POSTGRES_ENTRA_AUTHENTICATION=true` requires
  `APP_POSTGRES_MANAGED_IDENTITY_CLIENT_ID` (a user-assigned identity client UUID),
  TLS and no password variable. It uses `ManagedIdentityCredential`, never
  `DefaultAzureCredential` or ambient CLI login, and closes the credential after
  the database lifespan, including startup failure. The runtime `database`
  extra already supplies `azure-identity`.
- Redis composes the runtime shared rate store with bounded client timeouts and
  shutdown. `APP_RATE_LIMIT` is mandatory. The runtime fails open on cache
  outage; this is not a billing or authorization boundary.
- Entra bearer uses the public validator lifecycle and guards the technical
  `/technical/identity` endpoint with explicit required scopes/roles. There is
  no browser login or business route. Health remains public.
- Text generation puts the runtime `TextGenerator` on app state during serving,
  with no paid anonymous endpoint or automatic inference call. Consumers inject
  it into their authorized application service. The public port has no close
  method; the generated lifespan removes the reference on shutdown.

Only opted-in PostgreSQL/Redis containers appear in Compose, behind explicit
profiles. Configure `.env`, start selected profiles and run the local API.
For containerized app execution, Compose overrides dependency hosts to service
names. Host-process settings use loopback; published ports bind to loopback.
Remote databases require TLS. Remote Redis requires TLS and private networking.

## Verification boundaries

See the [deployment guide](DEPLOYMENT.md) for deployment contracts and operator
prerequisites. Cloud provisioning assigns the runtime identity to ACA, but a
separate PostgreSQL Entra administrator must create its database principal and
grant least-privilege access. The app is never silently made an administrator.
Private data-plane checks need a VNet/DNS-capable runner; production uses an
internal ACA environment, not app-only ingress isolation. Exact stages, separate
Terraform state keys, protected preview/apply and immutable pins are retained.

Generated tests use synthetic configuration and dependency substitutes; they are
not live database, Redis, Entra, model, image or cloud certification. Selected
authentication needs a real registration/JWKS access to validate real tokens.
Real AI inference needs separately approved provider credentials and may cost
money. Production migrations, secrets, federation, permissions and approvals
remain consumer/operator work.

This is not a verified idea-to-full-app-in-five-minutes installer. A local
health app can start quickly after published artifacts and dependencies are
available; download and setup times are not measured guarantees. Cloud
provisioning and release readiness are separate, unmeasured workflows.
Tag-to-tag Copier update qualification also remains outside this slice.
