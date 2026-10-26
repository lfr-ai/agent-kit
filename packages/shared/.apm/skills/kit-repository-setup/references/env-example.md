# Environment example files

`.env.example` documents every environment variable the application reads, so
a new contributor can create a local `.env` without asking anyone and a
reviewer can see configuration changes in a diff. It is documentation, never
configuration with real values. Review date: 2026-10-23.

## Rules

1. **Every variable the code reads is listed**, and nothing else. Compare the
   file against the settings class or the `os.environ` lookups in the same
   change that adds or removes a variable.
2. **Every variable has a comment directly above it** stating purpose,
   format or unit, whether it is required, and its default.
3. **Values are placeholders only.** Use an empty value, an obvious
   placeholder (`change-me`, `<api-key>`), a `localhost` or `example.com`
   URL, or a harmless local default such as a port or log level. Never a
   real key, password, token, internal host name or personal address.
4. **Group by concern** with a heading comment: application, server, database,
   cache, external services, observability, feature flags.
5. **Use one naming scheme**: upper case with underscores and a shared prefix
   when several applications share an environment (`APP_DATABASE_URL`).
6. **Do not quote unless the format needs it**, and keep one variable per
   line without `export`, so `.env` loaders and Docker `--env-file` agree.
7. **Commit `.env.example`, ignore `.env`**: add `.env` and `.env.*` to
   `.gitignore` with an exception for `.env.example`.
8. **Secrets in deployed environments come from a secret store**, not from a
   copied `.env`. The example names the variable; the platform supplies it.

## Placeholder classification

| Value | Accepted | Why |
| --- | --- | --- |
| empty (`API_TOKEN=`) | yes | forces an explicit choice |
| `change-me`, `<token>`, `your-...`, `example` | yes | obviously not real |
| `http://localhost:8000`, `https://api.example.com` | yes | reserved or local hosts |
| `info`, `8000`, `true`, `30` | yes, when they are safe defaults | not sensitive |
| local database URL with documented throwaway credentials | only with a comment that it is the local dev container | never a production credential |
| anything resembling a key (`sk-...`, `ghp_...`, long random strings) | no | indistinguishable from a leak |
| internal host names, IP ranges, e-mail addresses | no | discloses infrastructure or people |

The [repository file checker](../assets/check_repository_files.py) applies a
conservative version of this table: it accepts empty values, known placeholder
words, local hosts, numbers and booleans and reports everything else, plus any
variable without a comment line directly above it.

## Failure modes

- A new variable is read in code but missing from the example, so the app
  fails at startup for everyone else.
- A developer copies their working `.env` over the example and commits a key.
  Rotate the key first, then remove it from history with the operator.
- Example values drift from defaults in the settings class; keep defaults in
  code and say "default: X" in the comment.

## Verification

```text
python check_repository_files.py --root . --env-file .env.example
```

Then start the application with only the example values plus the minimum
required secrets and confirm it reports missing required variables clearly.

## Primary sources

- [The Twelve-Factor App: Config](https://12factor.net/config)
- Docker, [Set environment variables](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/)
- Pydantic, [Settings management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- OWASP, [Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
