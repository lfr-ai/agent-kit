---
description: Apply the local typed Python contract to toolkit code, scripts, tests, and portable templates.
applyTo: "src/**/*.py,tests/**/*.py,packages/**/*.py,scripts/**/*.py,**/*.py.template"
---

- Inject I/O so selection and validation are tested without files or processes.
- Use concrete types; no casts, production `Any` or quoted forward refs. Dataclasses are keyword-only; records are frozen and slotted.
- Name numbers other than 0 and +/-1 in `UPPER_CASE`; private `_UPPER` constants stay unannotated, public ones use `Final[T]`.
- Closed enums are `@unique`; `StrEnum` members use `auto()` when the value is the lowercase name.
- Use native naming (`SMTPFactory`); folders name the role, modules the responsibility (`infrastructure/apm.py`). Shared knowledge has one semantic owner.
- Name the parts of conditions with three or more operands; guard `None` early. Meet Ruff limits with helpers, not suppressions.
- Docstrings use double-backtick literals. A callable with at most one input (besides `self`/`cls`) gets a one-line summary that names the result and any error it raises, never `Args:`/`Returns:`/`Raises:` sections; sections are for several inputs and parameterized initializers. Properties read like attributes and classes use `Attributes:`. `Raises:` lists only what the body raises, translates or re-raises. The conventions gate enforces `kit-python-service/references/docstrings.md`.
- Comment non-obvious intent only. Catch specific failures; log once at the owning boundary with stdlib `logging`; report actionable, credential-free diagnostics.
- Use temporary test workspaces, never personal configuration or real cloud data.
- Do not assume the consumer contains the toolkit.
