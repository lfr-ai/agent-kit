# Pydantic v2 model boundaries

## Placement

- Use Pydantic models for untrusted transport input, response DTOs, configuration, and contracts that need validation or schema generation.
- Prefer keeping Core entities, value objects, and policies independent of `BaseModel`; convert at the owning adapter or presentation boundary when isolation is required. Intentional `BaseModel` use in Core is an explicit trade-off to evaluate, not an automatic architecture disqualifier.
- Prefer one model per distinct wire contract. Do not return an internal/domain model directly just because it serializes.
- Use standard dataclasses or `TypedDict` when validation, model behavior, and schema generation are not needed.

## Configuration

- Declare per-model options with `model_config = ConfigDict(...)`; avoid inheriting a global config that silently changes unrelated contracts.
- At external input boundaries, consider `extra='forbid'` so misspelled or unexpected fields do not disappear silently.
- Decide coercion/strictness from the actual wire contract. Strict mode is not a substitute for field-level constraints or explicit parsing.
- Use `from_attributes=True` only for a deliberate attribute-based adapter boundary; it does not justify importing ORM types into Core.
- Set `frozen=True` only when the instance should be immutable; this is shallow model immutability, not deep freezing of nested mutable values.
- `BaseSettings` is provided by the separate `pydantic-settings` distribution. Keep it in the configuration/composition boundary and keep secret values out of templates, defaults, reprs, and logs.

## Fields and defaults

- In v2, `T | None` describes nullability; it does not make a field optional without an explicit default.
- Use `Annotated` for reusable constraints and metadata. Use assignment-form `Field(default=...)`, `default_factory=...`, or `alias=...` when static type checker constructor synthesis depends on those arguments.
- Prefer factory defaults for mutable state even though Pydantic may copy unhashable defaults; the factory makes intent explicit.
- Keep validation and serialization aliases distinct when input and output wire names differ. Test `model_dump(by_alias=True)` explicitly.
- Treat generated JSON Schema as a public contract when a client, OpenAPI document, or downstream tool consumes it.
