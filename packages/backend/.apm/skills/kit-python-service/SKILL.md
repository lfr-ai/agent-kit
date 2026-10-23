---
name: kit-python-service
description: Use when implementing a typed Python service, boundary adapter, or endpoint.
license: MIT
---

# Implement a Python capability

## Procedure

1. Inspect the actual package layout, package manager, contracts, and scoped
   rules. Identify the layer of every file you will touch using
   [package layout and composition root](references/package-layout.md).
2. Write a failing regression for the expected behavior through the public
   interface ([service tests](assets/test_service.py.template) show the fake-port
   style).
3. Place domain rules inward. Inject file, database, HTTP, clock, or model
   boundaries as `typing.Protocol` ports through keyword-only constructors; wire
   concrete adapters only in the
   [composition root](assets/composition_root.py.template).
4. Design signatures per [signature design](references/signature-design.md):
   full annotations, keyword-only options, no positional `bool`, explicit units,
   one return shape.
5. Model records and closed value sets per
   [dataclasses and enums](references/dataclasses-enums.md), starting from the
   [record](assets/dataclass.py.template) and [StrEnum](assets/enum.py.template)
   templates.
6. Choose between conditionals and polymorphism with
   [polymorphism patterns](references/polymorphism.md); implement special
   methods only as described in [dunder methods](references/dunder-methods.md).
7. Translate boundary failures into specific documented errors per
   [error handling](references/error-handling.md). Chain with `from`; map to the
   transport only in presentation.
8. Load configuration once into typed [settings](assets/settings.py.template)
   and configure [logging](assets/logging_setup.py.template) once; follow
   [structured logging](references/logging.md). Keep personal data and secrets
   out of logs and `repr`.
9. Write docstrings per [docstring patterns](references/docstrings.md) and order
   code top-down per [method ordering](references/method-ordering.md).
10. Verify negative cases, types, import direction, and the project gate; run
    the bundled checkers below on the touched paths.

Avoid speculative layers or one-method wrappers without meaningful policy.

## Acceptance gates

- Public service API has unit and regression tests, including every documented
  error and at least one negative input per public operation.
- Error contracts are typed, documented in `Raises:`, and stable.
- No secrets or personal data in logs, exception messages, or `repr`.
- No production `Any`, `cast`, quoted forward references, or positional `bool`.
- Records are frozen, keyword-only, and slotted; enums persisted on the wire
  have explicit values.
- Presentation does not import infrastructure; the composition root is the only
  module that constructs adapters.
- The bundled checkers report no findings for the touched paths, or each
  remaining finding is an explicit, documented exception.

## Bundled checkers

All are standard-library scripts that parse source without importing it, print
`path:line: message`, and exit 1 on findings.

| Script | Purpose |
| --- | --- |
| [check_python.py](assets/check_python.py) | Double-backtick docstring literals, `Any`/`cast`, quoted annotations, initializer returns, dataclass options, bare `except`, opt-in `--bool-trap` and `--magic-numbers`. |
| [check_method_ordering.py](assets/check_method_ordering.py) | Private helper placed after its sole caller (`--order`, `--scope`, `--ignore`). |
| [check_backend_wiring.py](assets/check_backend_wiring.py) | Layer import rules (`--package`, `--forbid`, `--forbid-module`). |

```text
python check_python.py src --bool-trap --magic-numbers
python check_python.py tests --bool-trap
python check_python.py --only docstring-backtick packages
python check_python.py --templates --only magic-number packages
python check_method_ordering.py src
python check_backend_wiring.py src --package shop --forbid presentation:infrastructure
```

## Templates

| Template | Test template |
| --- | --- |
| [dataclass.py.template](assets/dataclass.py.template) | [test_dataclass.py.template](assets/test_dataclass.py.template) |
| [enum.py.template](assets/enum.py.template) | [test_enum.py.template](assets/test_enum.py.template) |
| [service.py.template](assets/service.py.template) | [test_service.py.template](assets/test_service.py.template) |
| [settings.py.template](assets/settings.py.template) | [test_settings.py.template](assets/test_settings.py.template) |
| [composition_root.py.template](assets/composition_root.py.template) | [test_composition_root.py.template](assets/test_composition_root.py.template) |
| [logging_setup.py.template](assets/logging_setup.py.template) | [test_logging_setup.py.template](assets/test_logging_setup.py.template) |

Templates use the placeholder package `shop`; rename imports when copying.
Native role procedures for this profile live in [agents.json](assets/agents.json).

## Docstrings

- Use `"""..."""` for every docstring, including one-liners; use raw strings for
  literal backslashes.
- Mark inline code with paired double-backtick reStructuredText literals in
  Python docstrings. Do not mark code with single quotes or single backticks.
  Markdown prose keeps normal CommonMark single-backtick syntax.
- Keep summaries useful and concise. Expand Google-style sections only for
  caller-relevant semantics, constraints, side effects, and expected failures.
- Google permits descriptive or imperative summaries, consistently within a file,
  and does not require repeating types already annotated in the signature.
- Sphinx/reStructuredText renders double-backtick literals as code. The local
  conventions gate enforces paired double backticks in docstrings; it does not
  change Markdown file syntax.

## References

- [Service guide](references/guide.md): review checklist, failure modes, recovery.
- [Signature design](references/signature-design.md)
- [Docstring patterns](references/docstrings.md)
- [Method ordering](references/method-ordering.md)
- [Polymorphism versus conditionals](references/polymorphism.md)
- [Dunder methods](references/dunder-methods.md)
- [Dataclasses and enums](references/dataclasses-enums.md)
- [Structured logging](references/logging.md)
- [Error handling](references/error-handling.md)
- [Package layout and composition root](references/package-layout.md)

Sources: [Google Python guide](https://google.github.io/styleguide/pyguide.html#381-docstrings)
and [PEP 257](https://peps.python.org/pep-0257/).
