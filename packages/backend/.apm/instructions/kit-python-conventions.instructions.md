---
description: Apply to Python language conventions covering types, dataclasses, imports, docstrings, and logging.
applyTo: "**/*.py,**/*.py.template"
---

- Use concrete types and explicit errors; no `Any`, casts, or quoted forward references in production code. Use built-in generics and `X | None`.
- Annotate signatures. Private `_UPPER` module constants stay unannotated; public `UPPER` constants use `Final[T]`, which prevents rebinding, not mutation.
- Prefer `frozen=True`, `kw_only=True`, `slots=True` dataclasses for value records and `Protocol` for injected collaborators.
- Closed wire sets are `@unique` `StrEnum`s using `auto()` when the value is the lowercase member name; keep other values explicit and test serialized values.
- Use `TypedDict` for known dict shapes, `TypeIs` only for exact predicates (otherwise `TypeGuard`), and `Annotated` only when a framework consumes it.
- Use `pathlib.Path`, explicit text encodings and absolute imports; no I/O, wildcard imports or side effects at import time.
- Raise specific exceptions with actionable messages; chain causes with `raise ... from error`.
- Make optional parameters keyword-only; name numeric literals other than `0` and `1`/`-1` by intent and unit; do not repeat a callee's defaults.
- Public APIs get Google-style docstrings with double-backtick literals: one line when the name and signature tell the story, attribute-style properties, `Attributes:` on classes, and sections only when they clarify. A non-initializer callable with at most one input never carries sections; fold its result and raised errors into the summary ([docstrings](../skills/kit-python-service/references/docstrings.md)). `Raises:` lists what the body raises, translates or re-raises, not callee failures; Protocol and abstract contracts are exempt.
- Use native naming with uppercase acronyms (`SMTPFactory`). Keep `None`/`isinstance` checks at untrusted boundaries.
- Return booleans directly; guard `None` early.
- Log via `logging.getLogger(__name__)` once, at the handling boundary, with lazy `%` arguments and redacted values. No `print` diagnostics, mutable defaults, bare `except` or runtime `assert`.
- Add a decorator only for cross-cutting behavior with two or more consumers; wrap with `functools.wraps` and `ParamSpec`.
- Use `kit-python-service` and its `check_python.py --docstrings` gate for callable, docstring, module and decorator detail.
