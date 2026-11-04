---
description: Apply to Python language conventions covering types, dataclasses, imports, docstrings, and logging.
applyTo: "**/*.py"
---

- Use concrete types and explicit errors; do not use `Any`, casts, or quoted forward references in production code.
- Annotate public functions and methods; mark module constants `Final` (bare `Final` lets the type be inferred) and never annotate private `_UPPER` constants with anything else. Use built-in generics (`list[str]`) and `X | None`.
- Prefer immutable, keyword-only, slotted dataclasses (`frozen=True`, `kw_only=True`, `slots=True`) for value-like records.
- Use `Protocol` for injected collaborators and `Enum` or `Literal` for closed value sets instead of bare strings.
- Use `TypedDict` for existing dict-shaped records with known keys, not a union of unrelated value types. It provides static types, not runtime validation. Use `TypeIs[T]` only when the predicate accepts every value of `T` and rejects every non-`T`; it narrows both branches. Keep `TypeGuard[T]` for partial validators such as nonempty strings, and for incompatible invariant input/output types. Use `Annotated` only when the framework consumes its metadata; otherwise use a direct type.
- Use `pathlib.Path` for paths, open text files with an explicit encoding, and keep I/O out of import time.
- Keep imports absolute and local to the layer that owns them; no wildcard imports or import-time side effects.
- Raise specific exception types with actionable messages and chain the cause with `raise ... from error`.
- Make optional parameters keyword-only when a function takes more than one; name numeric literals other than `0` and `1`/`-1` as `UPPER_CASE` constants that state intent and unit (tests may keep literal expectations). Do not repeat a callee's default value at a call site; pass only the arguments that differ.
- Use paired double-backtick literals for inline code in Python docstrings; Markdown prose keeps CommonMark single-backtick syntax. Use triple-double-quoted Google-style docstrings for public modules, classes, and functions, including the arguments of parameterized initializers.
- Use a one-line docstring when its summary captures the contract. Use multiline prose or sections for meaningful input constraints, effects, failures or structured results; parameter count and visibility do not determine length. Document initializer arguments in explicit prose or `Args:`. Supplied `Args:`, `Returns:` and `Yields:` sections include types and meaning; structured results describe fields, ordering and empty cases. Comments explain non-obvious intent, not the next statement.
- Use stdlib `logging` through `logging.getLogger(__name__)`; log once at the boundary that handles the error, with lazy `%` arguments, and redact sensitive values before emission.
- Do not use `print` for diagnostics, mutable default arguments, bare `except`, or `assert` for runtime validation.
- Introduce a decorator only for cross-cutting behavior with at least two current consumers. Transparent wrappers use `functools.wraps` and `ParamSpec` with the result type; metadata alone does not preserve async, generator, or descriptor behavior.
- Use `kit-python-service` for callable, docstring and module conventions; keep partial bindings and decorator effects explicit and test their observable contracts.
