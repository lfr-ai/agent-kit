# Twelve-factor configuration in practice

## What counts as configuration

Configuration is everything that varies between deploys of the same build:
endpoints of backing services, credentials, feature switches that operators flip
per environment, resource limits, and the identity of the deployment itself.
Code-level wiring that is identical everywhere (route tables, dependency graphs,
default page sizes that are part of a contract) is not configuration; keep it in
code where reviewers can see it change.

A useful test: if the repository were published publicly right now, would any
value need to be removed? Every such value belongs outside the source tree.

## Environment variables as the delivery channel

- The process receives settings as environment variables or mounted secret files
  provided by the runtime platform. The application never chooses its own
  environment by guessing a hostname or a path.
- Environment variables are granular and orthogonal. Avoid grouping settings into
  named "environments" inside code (`if env == "staging": ...`), which multiply
  as deploys grow and hide what actually differs.
- A local `.env` file is a developer convenience that mimics the platform. It is
  never committed and never read in production unless the platform itself
  mounts it.
- Collections and nested values can be passed as JSON strings or with a nested
  delimiter; choose one convention per project and document it.

## One build, many deploys

- Build artifacts (wheels, containers, executables) contain no deploy-specific
  values. The same artifact is promoted through every stage.
- The release step combines the artifact with the stage's configuration; the run
  step executes that release. Changing configuration produces a new release
  without a rebuild.
- Configuration changes are therefore deploy events: record them, roll them out
  gradually where possible, and support rollback just as for code.

## Naming

- Prefix all variables with an application-specific prefix (for example
  `ORDERS_`) so unrelated platform variables cannot collide with your fields.
- Use upper snake case and consistent suffixes: `_URL`, `_SECONDS`, `_BYTES`,
  `_ENABLED`. A unit in the name prevents a whole class of misconfiguration.
- Name the meaning, not the vendor: `ORDERS_CACHE_URL`, not `ORDERS_REDIS_HOST`,
  unless the setting truly only applies to that vendor.

## Precedence

A single, documented precedence order removes "which value won?" incidents. A
common order, from highest to lowest:

1. Explicit constructor arguments (tests and composition-root overrides).
2. Command-line arguments, when the application exposes them.
3. Process environment variables.
4. A local dotenv file (developer machines only).
5. Mounted secret files.
6. Code defaults for genuinely safe, non-secret values.

Pick an order, encode it once in the settings class, and test it; see
[settings layering](settings-layering.md).

## Anti-patterns

- Reading `os.environ` at import time in arbitrary modules. Values become
  frozen before tests can override them, and the dependency is invisible. Run
  [check_from_config_pattern.py](../assets/check_from_config_pattern.py) to find
  these reads.
- Defaulting to production endpoints. A missing value should fail, not silently
  talk to a live system.
- Encoding secrets in container images, CI logs, or crash reports.
- Using configuration as a feature database. Long-lived product toggles with
  targeting rules belong in a feature-flag service, not in environment variables.

## Sources

- <https://12factor.net/config>
- <https://12factor.net/build-release-run>
- <https://12factor.net/backing-services>
