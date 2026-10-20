---
description: Apply to Python language conventions covering types, dataclasses, imports, docstrings, and logging.
applyTo: "**/*.py"
---

- Use concrete types and explicit errors; do not use `Any`, casts, or quoted forward references in production code.
- Annotate every public function, method, and module constant; use built-in generics (`list[str]`) and `X | None`.
- Prefer immutable, keyword-only, slotted dataclasses (`frozen=True`, `kw_only=True`, `slots=True`) for value-like records.
- Use `Protocol` for injected collaborators and `Enum` or `Literal` for closed value sets instead of bare strings.
- Use `Annotated` only when the framework consumes its metadata; otherwise use a direct type.
- Use `pathlib.Path` for paths, open text files with an explicit encoding, and keep I/O out of import time.
- Keep imports absolute and local to the layer that owns them; no wildcard imports or import-time side effects.
- Raise specific exception types with actionable messages and chain the cause with `raise ... from error`.
- Make optional parameters keyword-only when a function takes more than one.
- Use triple-double-quoted Google-style docstrings for public modules, classes, and functions, including the arguments of parameterized initializers; mark inline code with 'single quotes', never backticks.
- Use stdlib `logging` through `logging.getLogger(__name__)`; log once at the boundary that handles the error, with lazy `%` arguments, and redact sensitive values before emission.
- Do not use `print` for diagnostics, mutable default arguments, bare `except`, or `assert` for runtime validation.
- Use the `kit-python-service` skill for the full docstring and module conventions.
