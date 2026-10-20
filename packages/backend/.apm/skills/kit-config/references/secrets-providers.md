# Secrets and secret providers

## Principles

- A secret is any value whose disclosure grants access: passwords, API keys,
  signing keys, connection strings with embedded credentials, client secrets.
- Prefer identity over secrets. A workload identity (managed identity, workload
  identity federation, instance roles) removes the secret entirely; the
  application asks the platform for a short-lived token.
- When a secret is unavoidable, it lives in a secret store and reaches the
  process at runtime. It never lives in source, images, CI variables printed to
  logs, or example files.
- Rotation is a normal operation. Design so that a rotated secret is picked up by
  a restart or a periodic refresh, and so that old and new values can overlap.

## Typing secrets

- Declare secret fields as `SecretStr` (or `SecretBytes`). Their `repr` and
  `str` are masked, and `model_dump()` keeps them wrapped. Call
  `get_secret_value()` only at the point where the client library needs the raw
  value.
- Never log the settings object with a custom serializer that unwraps secrets.
- Do not give secret fields defaults. A missing secret must fail startup.

## Delivery channels

| Channel | When to use | Notes |
| --- | --- | --- |
| Environment variable injected by the platform | Simple deployments | Visible to the process and its children; avoid echoing environment in diagnostics |
| Mounted secret file (`secrets_dir`) | Container orchestrators | One file per field; file permissions restrict readers |
| Secret store provider at startup | Central rotation and audit | Requires network and identity at startup; define timeout and failure behavior |
| Platform reference syntax resolved before start | Managed app platforms | The platform resolves the reference and injects a plain variable |

## Key Vault style providers

Cloud secret stores (for example Azure Key Vault, AWS Secrets Manager, Google
Secret Manager, HashiCorp Vault) are reached with a client library and a
credential. Two integration shapes are common:

1. **Settings source.** `pydantic-settings` ships an optional Azure Key Vault
   source (installed with the `azure-key-vault` extra) and supports custom
   sources. Insert it in `settings_customise_sources` so the provider fills
   fields that the environment did not set. Secret names in the vault usually
   cannot contain underscores; document the mapping (for example
   `orders-database-password` to `database.password`).
2. **Platform resolution.** The hosting platform resolves a vault reference and
   injects the value as an environment variable or file. The application stays
   provider-agnostic and the settings class sees an ordinary variable.

Either way:

- Authenticate with a workload identity in deployed environments and with a
  developer login locally; do not store a client secret for the vault itself in
  configuration.
- Bound provider calls with a timeout and fail startup with the secret name (not
  value) and the provider error category.
- Fetch secrets once at startup or through a refreshing cache; never per
  request.
- Grant the identity read access to the specific secrets it needs, not list or
  write access to the whole store.

## Local development

- Use a git-ignored `.env` file based on the committed
  [.env example](../assets/env.example.template). Placeholders must be obviously
  fake (`change-me`) so they cannot pass validation against a real service.
- Prefer a developer identity against a development vault over copying real
  secrets into local files.

## Diagnostics and redaction

- Startup errors name the field and the source, never the value. Pydantic
  validation errors include the input value by default; for secret fields use
  `SecretStr` so the input is masked, and avoid re-raising errors with the raw
  environment attached.
- Health or debug endpoints that display configuration show presence (`set`/
  `unset`) for secret fields.
- Scrub secrets from exception messages raised by client libraries before
  logging them when the library is known to include connection strings.

## Sources

- <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- <https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr>
- <https://learn.microsoft.com/azure/key-vault/general/overview>
- <https://learn.microsoft.com/azure/developer/python/sdk/authentication/overview>
- <https://12factor.net/config>
