---
description: Reorder Python modules and classes into one predictable layout and align private prefixes, suffixes and constant names without behavior change.
argument-hint: Python package, module, or path to reorder
agent: agent
---

# Align file ordering and naming

Give every module the same shape so readers know where to look.

## Input

- The user-supplied argument names the package, module, or path. When it is
  empty, use the Python files changed in the working tree.

## Procedure

1. Load [kit-python-service](../skills/kit-python-service/SKILL.md) and read
   the member and module order in its
   [idioms reference](../skills/kit-python-service/references/python-idioms.md)
   and the [method ordering](../skills/kit-python-service/references/method-ordering.md).
2. Record the prevailing order in the codebase; the project's existing
   convention wins over the default.
3. Module order: docstring, imports, constants, type aliases, exceptions,
   records and enums, public functions and classes, private helpers.
4. Class order: class attributes, `__init__` and other dunders, constructors,
   properties, public methods, private methods.
5. Names: `_private` for module internals, `UPPER_CASE` named constants with
   units instead of magic numbers, one suffix per role (`Port`, `Adapter`,
   `Service`, `Error`), verbs for functions, nouns for records.
6. Move code without editing it; rename through every caller, test, config,
   and doc reference in the same change.
7. Run the formatter, linter, type checker, and focused tests.

## Acceptance gates

- [ ] Each touched module follows one order; the diff only moves or renames.
- [ ] No old name remains in code, tests, or documentation.
- [ ] Lint, types, and tests pass with unchanged assertions.

## Output

Modules reordered, renames with caller counts, constants introduced, and the
commands run with results.
