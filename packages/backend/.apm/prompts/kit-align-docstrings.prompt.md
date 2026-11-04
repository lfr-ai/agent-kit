---
description: Make Python docstrings simple - one line by default, Google sections only when they add information - enforced by the bundled checker.
argument-hint: Python package, module, or path to align
agent: agent
---

# Align Python docstrings

Make every docstring say what the signature cannot, and nothing more.

## Input

- The user-supplied argument names the package, module, or path. When it is
  empty, use the Python files changed in the working tree.

## Procedure

1. Load [kit-python-service](../skills/kit-python-service/SKILL.md) and its
   [docstring patterns](../skills/kit-python-service/references/docstrings.md).
   Project lint configuration wins where it is stricter.
2. Run `check_python.py --docstrings <path>` and the project's pydocstyle and
   pydoclint rules. Collect findings grouped by rule.
3. Default to one line: an imperative summary that also states a non-obvious
   return or failure, for example
   `"""Write hook context; return 1 if stdin is oversized or invalid."""`.
4. Keep `Args:` only for public callables with two or more parameters or when a
   parameter has a unit, range, or constraint. List every parameter in
   signature order as `name (type): meaning`.
5. Keep `Returns:` only for structured values; keep `Raises:` for exceptions
   callers handle; use `Yields:` for generators.
6. Delete narration of the implementation, restated types, and section stubs.
   Prefer single-line `#` comments that state why, never what.
7. Module and class docstrings state ownership and invariants in one or two
   lines; initializer arguments go on `__init__`.
8. Re-run the checker, linter, and focused tests.

## Acceptance gates

- [ ] Docstring checker and lint findings for the path are zero.
- [ ] No docstring repeats the signature or narrates the code.
- [ ] Code, names, and behavior are unchanged.

## Output

Counts converted to one line, sections removed or added with an example
`path:line`, remaining findings with reasons, and commands run with results.
