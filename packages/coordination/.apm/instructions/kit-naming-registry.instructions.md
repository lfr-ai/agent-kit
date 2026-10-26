---
description: Apply to the shared naming registry and the modules generated from it.
applyTo: "**/naming_registry.json,**/naming_registry.schema.json,**/registry/**"
---

- The registry JSON is the only source for shared routes, query keys, event names, enum values, error codes, and field names; generated Python and TypeScript modules are never edited by hand.
- Change the registry, run `check_registry.py`, regenerate with `generate_registry.py`, and commit the registry and generated files in one change.
- Never change an existing value or reuse it with a new meaning; add a new entry and deprecate the old one with `since`, `reason`, `replacement`, and `remove_after`.
- Remove active entries only after a deprecation release and the `remove_after` version; persisted values need a data migration first.
- Increment `version` on every registry change following Semantic Versioning.
- Follow the naming rules: `PascalCase` groups, `UPPER_SNAKE_CASE` entries, kind-specific value patterns, single-line descriptions without quotes or backslashes.
- Use the `kit-naming-registry` skill for the full procedure and CI drift check.
