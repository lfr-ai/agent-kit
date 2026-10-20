# Refactoring blast radius

Refactors change structure without intending to change behavior. The blast
radius is everything that must change with the refactor, plus everything that
could change behavior by accident. Measure it before starting, keep each step
inside it, and enforce the new structure afterwards.

## Measure before moving

| Refactor | Graph query | Extra checks |
| --- | --- | --- |
| Rename a symbol | Text search for the name, word-bounded, all file types | Serialized names, configuration, docs, public exports |
| Move a module | `--reverse <module>` without depth limit | String module paths, entry points, mocks patched by dotted path |
| Split a module | `--reverse` for the module and the symbols each new module will own | Circular imports between the new modules |
| Merge modules | `--forward` for each module | New cycles introduced by the union |
| Delete code | `--reverse` plus text search plus blind spots | Dynamic lookups; published API |
| Extract a package | `--json` export, then group edges crossing the new boundary | Dependency direction into and out of the new package |

Record the counts. A rename touching 40 files across three packages is not the
same review as one touching four files in one package.

## Plan steps that stay green

1. **Introduce, then migrate, then remove.** Add the new location or name
   while the old one still works (re-export or thin alias), migrate callers in
   batches, then remove the old path. Each step keeps the build and tests
   passing.
2. **One kind of change per step.** Do not move and modify behavior in the
   same diff; reviewers cannot separate the two.
3. **Batch by ownership.** Migrate callers package by package so each owner
   reviews only their part.
4. **Watch for new cycles.** Run the cycle check after each step; splitting a
   module often creates a cycle between its halves.
5. **Patch targets.** Tests that patch by dotted path (`patch("shop.orders.x")`)
   must move with the symbol; search for the old dotted path in tests.

## Enforce the new shape

After the refactor, encode the intended structure so the graph does not drift
back:

- Layers: higher layers may import lower layers, not the reverse.
- Forbidden: a package must not import another (for example, domain code must
  not import web frameworks).
- Independence: sibling feature packages must not import each other.

Start from [the import-linter contract template](../assets/importlinter.ini.template)
for Python; use the equivalent dependency rules for other stacks. Add the
check to CI in the same change, with any temporary `ignore_imports` entries
listed, owned and dated.

## Verify

- Cycle check passes (or the remaining cycles are listed with owners).
- Reverse query for the old location returns nothing; text search for the old
  dotted path returns only the deliberate compatibility alias, if any.
- Full test suite passes; public API snapshot or documentation is unchanged
  unless the refactor was meant to change it.
- Contract check passes in CI.

## Anti-patterns

- Big-bang moves that touch every package in one diff.
- Deleting the compatibility alias before external consumers migrate.
- Adding broad `ignore_imports` entries to make a new contract pass.

## Sources

- [import-linter documentation](https://import-linter.readthedocs.io/en/stable/)
- [import-linter layers contract](https://import-linter.readthedocs.io/en/stable/contract_types/layers/)
- [unittest.mock: where to patch](https://docs.python.org/3/library/unittest.mock.html#where-to-patch)
- [Python import system](https://docs.python.org/3/reference/import.html)
