---
name: kit-config
description: Use when adding or changing application configuration with explicit validation, precedence, and secret handling.
license: MIT
---

# Treat configuration as untrusted boundary input

## Procedure

1. Find the authoritative settings model, its environment mapping, and the documented precedence. If none exists, create one root settings class from the [settings template](assets/settings.py.template).
2. Classify each value: deploy-specific configuration, secret, or code constant. Only the first two belong in settings; see [twelve-factor configuration](references/twelve-factor.md).
3. Declare every field with a precise type, bounds, and a unit in its name. Required values have no default; safe defaults are allowed only for non-secret values.
4. Group related fields into frozen nested facets (database, outbound client, TLS) so collaborators receive only what they need.
5. Encode the precedence order once in the settings class and test it; see [settings layering](references/settings-layering.md).
6. Type secrets as `SecretStr`, give them no defaults, and choose a delivery channel or provider; see [secrets and providers](references/secrets-providers.md).
7. Parse once at the entry point before building any adapter. Report every invalid field by variable name without its value; see [startup validation](references/startup-validation.md).
8. Pass facets explicitly from the composition root into adapters. Domain and application code never import settings or read the environment.
9. Run [check_from_config_pattern.py](assets/check_from_config_pattern.py) on source directories to find environment access outside settings modules. Mark reviewed exceptions inline with `# config: env-access-reviewed`.
10. Update the committed [.env example](assets/env.example.template) and the operator documentation for every added, renamed, or removed variable. Placeholders must be obviously fake.
11. Copy and adapt the [settings tests](assets/test_settings.py.template): missing, malformed, boundary, precedence, cross-field, immutability, and secret masking.
12. For renamed variables, accept both names with `AliasChoices` for one release, log nothing about the value, then remove the old name.
13. Keep the [required keys list](assets/required_keys.json.template) in sync when deployment tooling checks manifests against it.
14. Read the [configuration guide](references/guide.md) for failure modes and recovery.

## Acceptance gates

- One settings class (with facets) is the only module that reads the process environment; the checker reports no unreviewed findings.
- Every required value fails startup when absent or malformed, with the variable name in the message.
- No secret has a default, appears in an example with a realistic value, or is printed by `repr`, logs, or error output.
- Precedence between arguments, environment, dotenv, and secret files is documented and covered by a test.
- Domain and application layers receive plain values or facets through constructors; no module-level settings singleton is imported outside the composition root.

## Commands

```text
python assets/check_from_config_pattern.py src --allow "*settings.py" --exclude "*/tests/*"
python assets/check_from_config_pattern.py --self-test
pytest tests/unit/test_settings.py -q
```

## Failure modes to test

- Missing required variable, misspelled prefix, or wrong nested delimiter.
- Conflicting values in environment and dotenv with an unexpected winner.
- Malformed typed values: non-integer counts, invalid URLs, unknown modes.
- Secret exposure in logs, exception text, or serialized settings.
- Provider timeouts or permission errors at startup.
