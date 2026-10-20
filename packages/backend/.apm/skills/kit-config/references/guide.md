# Configuration guide

## Purpose

Change application configuration safely: classify values, validate them once at
startup, preserve a documented precedence, keep secrets out of artifacts, and
pass typed values explicitly to the code that needs them.

## Map of this skill

| Topic | Reference or asset |
| --- | --- |
| What is configuration, naming, precedence | [twelve-factor](twelve-factor.md) |
| `pydantic-settings` sources, nesting, customization | [settings layering](settings-layering.md) |
| Secret typing, stores, rotation, redaction | [secrets and providers](secrets-providers.md) |
| Fail-fast parsing and explicit dependency passing | [startup validation](startup-validation.md) |
| Copyable root settings with facets | [settings template](../assets/settings.py.template) |
| Developer example file | [.env example](../assets/env.example.template) |
| Contract tests | [settings tests](../assets/test_settings.py.template) |
| Hidden environment reads | [checker](../assets/check_from_config_pattern.py) |
| Deployment manifest key list | [required keys](../assets/required_keys.json.template) |

## Acceptance gates

- The settings model is in source control and documents every variable, its
  type, its bounds, and whether it is secret.
- Required keys are validated at startup with clear, value-free error messages.
- No secrets appear in committed defaults, examples, fixtures, or snapshots.
- A redaction policy covers logs, error output, and diagnostic endpoints.
- The environment is read in exactly one place.

## Failure modes

- Missing or misnamed environment variables causing startup failure, or worse, a
  silent fallback to a default that points at the wrong system.
- Conflicting values between files and the environment producing an unexpected
  winner because precedence was never written down.
- Malformed typed values (a string where an integer is expected, a URL without a
  scheme, a duration in the wrong unit).
- Secrets copied into checked-in defaults, example files, CI logs, or crash
  reports.
- Import-time environment reads that freeze values before tests or the
  composition root can override them.
- A secret provider that is slow or unreachable at startup, turning a deploy into
  a hang instead of a clear failure.

## Verification

- Run the settings contract tests with an isolated environment.
- Run the environment-access checker over source directories and review any
  waiver comments it skips.
- Compare the committed example and the required keys list with the deployment
  manifests the operator owns.
- Exercise provider-specific precedence in a safe, non-production environment.

## Negative cases

- Empty, null, or malformed values for required keys.
- Mutually exclusive options both supplied, or dependent options missing.
- Values just outside configured bounds.
- A secret value injected into an unrelated field to prove it is not echoed.

## Recovery and mitigation

- Fail fast on startup with the variable name, expected form, and a remediation
  hint; exit non-zero so orchestrators stop the rollout.
- Roll back a configuration change the same way as a code change: re-deploy the
  previous release.
- Allow a permissive fallback only behind an explicit, documented operator
  switch, and log that the fallback is active.

## Scope and limits

This skill covers configuration semantics, validation, and secret handling in
application code. It does not replace secret-store access reviews, platform
policy, or deployment orchestration checks. The checker is a static heuristic: it
cannot see environment access through dynamic imports or third-party libraries.

## Sources

- <https://12factor.net/config>
- <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- <https://docs.python.org/3/library/os.html#os.environ>
