---
description: Tighten Python type hints - complete, concrete, modern syntax, no Any or casts - and prove it with the project's type checker.
argument-hint: Python package, module, or path to type
agent: agent
---

# Align Python type hints

Make types precise enough that the checker, not a reader, catches mistakes.

## Input

- The user-supplied argument names the package, module, or path. When it is
  empty, use the Python files changed in the working tree.

## Procedure

1. Load [kit-python-typing](../skills/kit-python-typing/SKILL.md) and its
   [typing reference](../skills/kit-python-typing/references/typing.md). Read
   the project's type-checker configuration (for example `ty.toml`) first.
2. Run the type checker and focused tests for a green baseline.
3. Annotate every parameter and return, including `-> None`. Use built-in
   generics, `X | None`, `type` aliases, and `collections.abc` protocols for
   parameters; return concrete types.
4. Replace production `Any`, `cast`, `# type: ignore`, and quoted forward
   references with narrowing, `TypeGuard`/`TypeIs`, overloads, generics, or a
   refactored boundary. Use `object` at untyped parsing edges.
5. Replace loose dictionaries crossing a boundary with frozen dataclasses,
   `TypedDict`, `NamedTuple`, or `StrEnum`; use `Final` for constants.
6. Move type-only imports under `TYPE_CHECKING` only when the linter asks.
7. Re-run the type checker, linter, and focused tests after each module.

## Acceptance gates

- [ ] Type checker reports zero findings for the path.
- [ ] No production `Any`, `cast`, or blanket ignore remains.
- [ ] Tests pass with unchanged assertions.

## Output

Annotations added, escapes removed (with `path:line` examples), any remaining
escape with its reason, and the commands run with results.
