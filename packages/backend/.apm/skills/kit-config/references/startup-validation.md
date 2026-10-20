# Validate at startup and pass settings explicitly

## Fail fast, once

1. The entry point (CLI `main`, ASGI factory, worker bootstrap) constructs the
   root settings object before creating any client, pool, or thread.
2. Construction validates every field. Any failure stops the process with a
   non-zero exit and a message listing each invalid field, its source variable,
   and the expected form.
3. Cross-field rules (for example "TLS key required when TLS is enabled") are
   `model_validator(mode="after")` checks on the settings model, so they run at
   the same moment.
4. Optional reachability checks (database ping, vault access) run after parsing,
   with explicit timeouts, and are reported separately from parse errors so
   operators can tell "wrong value" from "unreachable service".

Do not lazily read a setting the first time a request needs it. A typo then
surfaces hours after deploy, under load, as a confusing runtime error.

## Typed values instead of strings

| Need | Type |
| --- | --- |
| Endpoint | `HttpUrl`, `AnyUrl`, or a DSN type such as `PostgresDsn` |
| Duration | `timedelta` or an `int` field named `*_seconds` with bounds |
| Size or count | `int` with `Field(ge=..., le=...)` |
| Mode switch | `Literal["json", "text"]` or an `Enum` |
| Secret | `SecretStr` |
| File path | `Path`, `FilePath`, or `DirectoryPath` |
| Flag | `bool` (accepts `true/false/1/0/yes/no/on/off`) |

Bounds are part of the contract. A pool size of zero or a timeout of one
million seconds should fail validation, not production.

## Explicit dependency passing

The domain and application layers never import the settings module and never
read the environment. Instead:

- The composition root builds settings, then builds adapters with the facets
  they need: `OrderRepository(settings.database)`,
  `InvoiceClient(base_url=settings.billing.url, timeout=settings.billing.timeout)`.
- Services receive collaborators, not settings. When a service needs a policy
  value (a retry limit, a page size), pass that value or a small frozen policy
  object.
- A module-level `settings = Settings()` singleton is avoided. It runs at import
  time, couples every importer to the environment, and forces tests to patch
  globals. If a framework needs a provider, expose a factory function and cache
  it at the composition root (for example with `functools.cache`) so tests can
  clear it.

This matches the hexagonal dependency direction: configuration is an outer-layer
concern that is translated into constructor arguments as it crosses inward.

## Detecting hidden configuration

- Run [check_from_config_pattern.py](../assets/check_from_config_pattern.py) on
  source directories. It reports `os.environ` and `os.getenv` use outside files
  that match `--allow` globs (defaults: `*settings.py`, `*settings/*.py`,
  `*config.py`, `*config/*.py`).
- Legitimate exceptions (for example passing the environment to a subprocess) are
  marked with the inline comment `# config: env-access-reviewed` so the waiver is
  visible in review.
- Treat a new finding as a design question: should this value be a settings
  field passed to the caller?

## Error message shape

A good startup failure is actionable without leaking values:

```text
Invalid configuration (2 errors):
  ORDERS_DATABASE__URL: missing; set a PostgreSQL URL such as postgresql://host/db
  ORDERS_HTTP_TIMEOUT_SECONDS: must be between 1 and 120 (got a non-integer value)
```

Render this from `ValidationError.errors()` using each error's `loc` and `msg`,
mapping `loc` back to the variable name with the configured prefix and nested
delimiter. Omit the `input` key for secret fields.

## Tests that prove the contract

- Missing required field fails with the field name.
- Malformed value (non-integer, bad URL) fails.
- Boundary values pass; just-outside values fail.
- Precedence: a constructor argument beats the environment; the environment
  beats dotenv.
- Secrets never appear in `repr(settings)`, `str(error)`, or JSON dumps.
- The composition root can be built from explicit settings without touching the
  environment.

The [settings test template](../assets/test_settings.py.template) covers each of
these.

## Sources

- <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- <https://docs.pydantic.dev/latest/concepts/validators/>
- <https://docs.pydantic.dev/latest/errors/errors/>
- <https://docs.python.org/3/library/functools.html#functools.cache>
