---
description: Apply in likely Pydantic transport DTO, request, response, and settings modules.
applyTo: "**/*dto*.py,**/*schema*.py,**/*request*.py,**/*response*.py,**/*settings.py"
---

- When using Pydantic, use v2 APIs and prefer explicit validation/serialization boundaries; if `BaseModel` is intentionally used in Core, document the isolation trade-off rather than treating it alone as an architecture failure.
- Use `model_validate`, `model_dump`, `field_validator`, `model_validator`, and `ConfigDict`; do not mix in v1 names such as `parse_obj`, `.dict()`, `@validator`, or `class Config`.
- Set `extra="forbid"` on inbound request models unless unknown fields are part of the contract.
- Express value rules with `Field` constraints and `Annotated` types; keep validators free of I/O.
- Keep transport models separate from domain and persistence types, and map between them explicitly.
- Read secrets through `pydantic-settings` as `SecretStr`, and never log or dump settings without excluding them.
- Read the project lockfile for the installed Pydantic minor and the `kit-pydantic-v2` skill before changing validators, aliases, or JSON output.
- Do not add v1 compatibility imports unless the project has an explicit migration plan.

See the [Pydantic v2 procedure](../skills/kit-pydantic-v2/SKILL.md).
