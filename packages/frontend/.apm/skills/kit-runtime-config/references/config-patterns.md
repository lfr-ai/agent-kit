# Runtime configuration patterns

## Build-time versus runtime

| Aspect | Build-time (`import.meta.env.VITE_*`) | Runtime (`/config.json` fetched at boot) |
| --- | --- | --- |
| When fixed | at `vite build`; inlined into JavaScript | at deployment; read on every page load |
| Artifacts | one build per environment | one build promoted through environments |
| Change requires | rebuild and redeploy | replacing one file or env-generated response |
| Typical content | app name, feature defaults for local development | API base URL, environment name, feature flags, telemetry sampling |
| Visibility | public | public |

Prefer runtime configuration whenever the same artifact must run in more than
one environment. Both mechanisms deliver values to every visitor; neither can
hold a secret.

## Building blocks

| Piece | Template |
| --- | --- |
| Schema, loader, accessors, test seam | [runtime-config.ts](../assets/runtime-config.ts.template) with [tests](../assets/runtime-config.test.ts.template) |
| Example deployed file | [config.json](../assets/config.json.template) |
| Typed build-time variables | [vite-env.d.ts](../assets/vite-env.d.ts.template) |
| Boot order with accessible failure screen | [main.tsx](../assets/main.tsx.template) |
| Built-output scanner | [scan_public_bundle.py](../assets/scan_public_bundle.py) |

Secret handling rules are in [public value boundaries](public-value-boundaries.md).

## Schema rules

- Strict object: unknown keys fail, which catches typos and accidental secret
  fields being added to the public file.
- URLs are absolute, `https` outside localhost, normalized with a trailing slash
  so relative API paths resolve predictably.
- Enumerate environments; do not branch on free-form strings.
- Feature flags are booleans with a naming pattern; defaults live in the schema,
  not scattered through components.
- Freeze the parsed object so no module mutates shared configuration.

## Boot sequence

1. Fetch `/config.json` with `cache: "no-store"` and a timeout.
2. Validate; on any failure render a static, accessible error with a reload
   action and log issues for operators.
3. Only then create the HTTP client, query client, router, and telemetry, all of
   which read configuration lazily through `getRuntimeConfig()`.
4. Never fall back silently to a default host: a wrong API host is worse than a
   visible startup error.

## Serving the file

- Generate `config.json` at deploy or container start from environment variables
  of the hosting platform, validate it with the same schema in the pipeline, and
  write it next to `index.html`.
- Serve it with `Cache-Control: no-store` (or a short max-age with revalidation)
  while hashed assets stay immutable.
- The Content Security Policy `connect-src` must include the configured API
  origin; keep both in the same deployment change.
- Version the shape: add fields as optional first, deploy the file, then make the
  frontend require them. Removing a field follows the reverse order.

## Testing

- Unit: valid file, each invalid field, unknown key, http outside localhost,
  non-JSON, HTTP error, network error (see the test template).
- Component tests: install config with `setRuntimeConfigForTests` in the shared
  setup; never fetch it.
- Browser: start the preview server with a test `config.json`; assert the app
  calls the configured origin.
- Release: run the bundle scanner on the build output before publishing.

```powershell
python scan_public_bundle.py dist --forbid-source-maps --deny "\.internal\.example\b"
```

The scanner prints `path:line: [rule] redacted-match; hint` and exits 1 on any
finding. It checks known patterns only; record its scope in the release notes
rather than claiming the bundle is secret-free.

## Anti-patterns

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| `VITE_API_KEY` for a private third-party API | key published to every visitor | proxy through the backend |
| `envPrefix: ""` or exposing all variables | server variables inlined into the bundle | keep the `VITE_` prefix; review additions |
| `config.apiUrl ?? "https://prod..."` fallback | test build calls production | fail visibly |
| Reading `window.__CONFIG__` without validation | malformed values crash later | parse with the schema |
| Separate builds per environment for URL changes | untested artifact reaches production | one artifact plus runtime file |
| Long cache on `config.json` | clients keep stale endpoints after a change | `no-store` |
| Source maps with `sourcesContent` on a public host | internal comments and paths exposed | upload maps to the error tracker privately |

## Acceptance gates

- [ ] One schema validates the file in the pipeline and in the browser.
- [ ] Startup fails visibly and accessibly on missing, malformed, or insecure
      configuration; tests cover each case.
- [ ] Clients and routers read configuration only after it loaded.
- [ ] `config.json` is served without long caching; CSP matches the API origin.
- [ ] The bundle scanner ran on the build output; scope and findings recorded.

## Sources

- Vite, env variables and modes: <https://vite.dev/guide/env-and-mode>
- Vite, `envPrefix`: <https://vite.dev/config/shared-options.html#envprefix>
- Vite, `build.sourcemap`: <https://vite.dev/config/build-options.html#build-sourcemap>
- Zod 4, strict objects: <https://zod.dev/api#objects>
- MDN, `fetch` cache modes: <https://developer.mozilla.org/en-US/docs/Web/API/Request/cache>
- MDN, `Cache-Control`: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control>
- MDN, `AbortSignal.timeout`: <https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static>
- The Twelve-Factor App, config: <https://12factor.net/config>
