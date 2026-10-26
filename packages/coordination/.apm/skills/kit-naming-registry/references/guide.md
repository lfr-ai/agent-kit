# Naming registry design and operation

Reviewed 2026-10-23 against Python 3.13 `enum`, TypeScript 5 handbook, JSON
Schema 2020-12, and Semantic Versioning 2.0.0.

## What belongs in the registry

| Identifier | Register when | Leave elsewhere when |
| --- | --- | --- |
| Route paths | Both stacks build or match the path by hand | A client is generated from the OpenAPI description |
| Query keys | Server pushes invalidations by key, or several clients share caches | Keys stay inside one frontend factory (`kit-state-data`) |
| Event names | Producers and consumers live in different stacks | One service emits and consumes |
| Enum values | Both stacks branch on the value | The value is display-only text |
| Error codes | The client maps codes to messages or recovery | Generic HTTP status is enough |
| Field names | Used in filters, sort parameters, or error pointers | Covered by generated request and response types |

The registry complements the API contract; it does not replace it. When both
define the same value, the API description wins and the registry references
it in review.

## Layout

```text
registry/
  naming_registry.json          # canonical source, reviewed like code
  naming_registry.schema.json   # structure; semantics live in the checker
backend/src/app/registry.py     # generated StrEnum classes
frontend/src/shared/registry.ts # generated const objects and union types
```

- Generated files carry a four-line header with the registry version, registry
  digest, and body digest. Never edit them; change the registry and regenerate.
- Exclude generated files from formatters and linters that rewrite code, or
  the body digest changes and the checker reports a hand edit.
- Both stacks import only from their generated module.

## Generation

| Output | Shape | Why |
| --- | --- | --- |
| Python | One `StrEnum` per group plus `REGISTRY_VERSION: Final` | Members compare equal to their string values and serialize as strings |
| TypeScript | One `as const` object per group plus a same-named union type | No runtime enum code; `OrderStatus.PAID` and type `OrderStatus` both work |
| Deprecations | Python comment; TypeScript `@deprecated` JSDoc | Editors and linters surface the warning at use sites |

The generator is deterministic and rewrites a file only when content changes,
so running it in CI and checking `git diff --exit-code` also works.

## CI drift check

```yaml
- name: Naming registry
  run: >-
    python tools/check_registry.py registry/naming_registry.json
    --python backend/src/app/registry.py
    --typescript frontend/src/shared/registry.ts
    --baseline build/released/naming_registry.json
```

Obtain the baseline from the last release tag (for example with
`git show <tag>:registry/naming_registry.json`) in an earlier step. Run the
check on every pull request that touches the registry, the generated files, or
either stack's imports of them.

## Versioning and deprecation

| Change | Version bump | Allowed directly |
| --- | --- | --- |
| Add a group or entry | Minor | Yes |
| Edit a description | Patch | Yes |
| Deprecate an entry | Minor | Yes, with `since`, `reason`, and usually `replacement` |
| Change an entry's value | Not allowed | Add a new entry, deprecate the old one |
| Remove a deprecated entry | Major, at or after `remove_after` | Yes, once no code references it |
| Remove an active entry | Not allowed | Deprecate first |

Consumers that persist values (databases, analytics, queued events) need a
data migration before removal; the registry check cannot see stored data.

## Failure modes

| Symptom | Cause | Repair |
| --- | --- | --- |
| Frontend shows unknown status | Backend added a value; frontend not regenerated | Regenerate both in one change; handle unknown values explicitly |
| Checker reports "edited by hand" | Formatter or manual edit changed the generated body | Exclude from formatter; regenerate |
| Checker reports "stale" | Registry changed without regeneration | Run the generator; commit both |
| Persisted values break after rename | Value changed in place | Add new entry, migrate data, deprecate old |
| Same event name means two things | Global uniqueness not enforced | Kind-wide uniqueness check |
| Duplicate keys silently overwritten | JSON objects with repeated keys | Checker's duplicate-key rule |

## Primary sources

- Python `enum.StrEnum`: <https://docs.python.org/3/library/enum.html#enum.StrEnum>
- TypeScript `as const` and literal types: <https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#literal-types>
- TypeScript enums versus objects: <https://www.typescriptlang.org/docs/handbook/enums.html#objects-vs-enums>
- JSDoc `@deprecated` in TypeScript: <https://www.typescriptlang.org/docs/handbook/jsdoc-supported-types.html#deprecated>
- JSON Schema 2020-12: <https://json-schema.org/draft/2020-12>
- Semantic Versioning 2.0.0: <https://semver.org/spec/v2.0.0.html>
- RFC 8259, JSON (duplicate names): <https://www.rfc-editor.org/rfc/rfc8259#section-4>
- RFC 9457, problem details (error codes as types): <https://www.rfc-editor.org/rfc/rfc9457>
