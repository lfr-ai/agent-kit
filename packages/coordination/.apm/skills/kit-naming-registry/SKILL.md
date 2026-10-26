---
name: kit-naming-registry
description: Use when backend and frontend share routes, event names, enum values or error codes that need one canonical registry.
license: MIT
---

# Keep shared identifiers in one registry

## Resources

- [Registry guide](references/guide.md): what belongs in the registry, file
  layout, generation, CI drift check, versioning and deprecation, failure
  modes, primary sources.
- [Naming rules](references/naming-rules.md): per-kind value patterns, constant
  and type names, reserved names, and examples.
- Templates: [registry](assets/naming_registry.json.template) and its
  [JSON Schema](assets/naming_registry.schema.json.template).
- Generator: [generate_registry.py](assets/generate_registry.py)
  (`REGISTRY`, `--python`, `--typescript`); deterministic Python `StrEnum` and
  TypeScript `as const` output with a provenance header.
- Checker: [check_registry.py](assets/check_registry.py)
  (`REGISTRY`, `--schema`, `--python`, `--typescript`, `--baseline`).
- Related owners: contract-first sequencing in `kit-fullstack-workflow`, file
  and module naming in `kit-consistency`, query key factories in
  `kit-state-data`, error shapes in `kit-api-contracts`.

## Procedure

1. Read the guide; list the identifiers both stacks must spell identically and
   who owns each kind.
2. Keep values that an API description already defines (paths, schemas) in
   that description; register only identifiers that cross the stack without a
   generated client, or that both sides use as constants.
3. Copy the registry and schema templates into one repository path that both
   stacks read, for example `registry/`.
4. Add groups by kind (`route`, `query_key`, `event`, `enum`, `error_code`,
   `field`) with a description; follow the naming rules for names and values.
5. Run `check_registry.py` until it reports no findings.
6. Generate the Python and TypeScript modules with `generate_registry.py`;
   commit the registry and generated files together; exclude generated files
   from formatters so their digests stay valid.
7. Import constants from the generated modules only; replace string literals in
   both stacks and add a test at each boundary that uses them.
8. Change values only by adding a new entry and deprecating the old one with
   `since`, `replacement`, `reason`, and `remove_after`; bump `version`.
9. In CI, run the checker with `--python`, `--typescript`, and `--baseline`
   (the registry from the last release) so drift, unsafe removals, changed
   values, and missing version bumps fail the build.
10. Remove deprecated entries only after `remove_after`, once both stacks no
    longer reference them.
11. Report checker output, generated paths, and boundary tests that ran.

## Acceptance gates

- [ ] The checker exits 0 with schema, semantics, baseline, and drift checks.
- [ ] Generated modules are committed, current, and never edited by hand.
- [ ] No hard-coded copies of registered values remain in either stack.
- [ ] Every changed value went through add, deprecate, remove with a version
      bump per step.
- [ ] CI runs the checker on every change to the registry or generated files.
