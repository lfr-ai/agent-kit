---
name: kit-pydantic-v2
description: Use when defining Pydantic v2 models, validators, serialization, or JSON Schema, or migrating from v1.
license: MIT
---

# Define Pydantic v2 schemas at boundaries

1. Read the consumer lockfile and installed Pydantic version. This skill targets v2; check version-specific APIs rather than assuming `latest`.
2. Prefer `BaseModel` at input/output, settings, and serialization boundaries. Convert to framework-independent domain values before Core where isolation is required; if Core intentionally uses Pydantic, document the isolation trade-off and assess its replacement cost rather than treating coupling alone as an architecture failure.
3. Use annotated field types and `ConfigDict`. Choose `extra`, strictness, mutability, and attribute loading per boundary; do not copy a universal config to every model.
4. Use `Annotated[T, Field(...)]` for reusable validation metadata. Keep `default`, `default_factory`, and `alias` assignment-form arguments where static type checkers need them.
5. Distinguish missing from nullable: `value: T | None` is still required unless it has an explicit default. Use `Field(default_factory=...)` for mutable defaults.
6. Prefer built-in constraints and `field_validator(mode='after')`; use `mode='before'` only to normalize raw input. Use `model_validator(mode='after')` for cross-field invariants and return the model.
7. Keep validators deterministic and side-effect-free. Raise `ValueError` for invalid values; never return success-shaped fallbacks or depend on another field unless its ordering is explicit.
8. Use `TypeAdapter` for validating, serializing, or generating schema for non-model types. Use `model_validate_json` for JSON input when its validator behavior is suitable.
9. Make serialization intent explicit: `model_dump(mode='json')`, `model_dump_json()`, and `by_alias=True` have different contracts. Test wire output and generated JSON Schema.
10. Do not expose secret fields in representations or outputs; use `SecretStr` where applicable and explicit response DTOs.
11. On v1 migration, replace deprecated APIs rather than keeping a `pydantic.v1` shim. Review coercion, required/nullable semantics, equality, aliases, validators, serialization, and JSON Schema.
12. `BaseSettings` lives in the separately installed `pydantic-settings` package. Keep settings at the composition/configuration boundary and never commit secret defaults.
13. Use the [request model](assets/request_model.py.template), [validator pattern](assets/cross_field_model.py.template), [settings](assets/settings.py.template), and [contract tests](assets/test_request_model.py.template); run them under the consumer's pinned Pydantic v2.
14. Tag every union of models with a discriminator and test missing and unknown tags; see [discriminated unions](references/discriminated-unions.md) and the [payment contract](assets/patterns/payments.py.template) with its [tests](assets/patterns/test_payments.py.template).
15. Decide strict versus lax coercion per boundary and per field; validate JSON text with `model_validate_json` so string-encoded types still parse in strict mode; see [strict mode](references/strict-mode.md).
16. Put representation changes on reusable annotated types or explicit serializers and test JSON output and round trips; see [custom serialization](references/custom-serialization.md).
17. On hot paths, build `TypeAdapter` instances once, prefer core constraints over Python validators, and measure before and after; see [performance](references/performance.md).
18. Run [check_pydantic_v2.py](assets/check_pydantic_v2.py) on source directories to find v1 APIs and shims; mark a reviewed exception with `# pydantic: reviewed`.

## Acceptance gates

- No `pydantic.v1` imports or v1 decorators, config keys, or methods remain unless explicitly reviewed.
- Every external input model states its `extra` policy, and every union of models has a discriminator.
- Wire output (`model_dump(mode='json')` or `model_dump_json()`) and externally consumed JSON Schema are asserted in tests.
- Secrets are typed `SecretStr` and never appear in reprs, dumps, or error output.
- Hot-path changes are justified by a measurement, not by assumption.

## Commands

```text
python assets/check_pydantic_v2.py src
python assets/check_pydantic_v2.py --self-test
pytest tests/unit/contracts -q
```

## Focused references

- [Model boundaries and configuration](references/model-boundaries.md)
- [Validation and serialization](references/validation-serialization.md)
- [v1-to-v2 migration review](references/migration-v1-to-v2.md)
- [Discriminated unions](references/discriminated-unions.md)
- [Strict mode and coercion](references/strict-mode.md)
- [Custom serialization](references/custom-serialization.md)
- [Validation and serialization performance](references/performance.md)

Sources: [models](https://pydantic.dev/docs/validation/latest/concepts/models/),
[fields](https://pydantic.dev/docs/validation/latest/concepts/fields/),
[validators](https://pydantic.dev/docs/validation/latest/concepts/validators/),
[serialization](https://pydantic.dev/docs/validation/latest/concepts/serialization/),
[JSON Schema](https://pydantic.dev/docs/validation/latest/concepts/json_schema/),
[performance](https://pydantic.dev/docs/validation/latest/concepts/performance/),
[settings](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/),
and [migration](https://pydantic.dev/docs/validation/latest/get-started/migration/).
