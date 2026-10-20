# Docstrings and generated API reference

Reference documentation for code should be generated from the code, so it
cannot drift from signatures and types. Docstrings carry what the signature
cannot: meaning, constraints, errors and examples.

## What a docstring states

For every public module, class, function and method:

- **Summary line**: one sentence in the imperative or descriptive mood that
  says what it does, not how. Ends with a period.
- **Arguments**: meaning, units, accepted range or format, and what `None`
  means. Types come from annotations; do not repeat them in prose.
- **Returns / yields**: what the value represents, including empty results.
- **Raises**: each exception a caller should handle and when it is raised.
- **Side effects**: I/O, mutation of arguments, global state, network calls.
- **Example**: a short, runnable usage example where the call is not obvious.

Private helpers need a docstring only when their behavior is not obvious from
the name and signature.

## Python: Google style

```python
def split_invoice(invoice: Invoice, *, parts: int) -> list[Invoice]:
    """Split an invoice into equal parts, assigning rounding to the last part.

    Args:
        invoice: The invoice to split. It is not modified.
        parts: Number of resulting invoices; must be at least 1.

    Returns:
        New invoices whose totals add up exactly to the original total.

    Raises:
        ValueError: If 'parts' is less than 1 or the invoice is already paid.

    Example:
        >>> [part.total for part in split_invoice(invoice_of(100), parts=3)]
        [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')]
    """
```

Consistency rules:

- Pick one style (Google, NumPy or reStructuredText field lists) per project
  and enforce it with a linter (Ruff `D` rules with the matching
  `pydocstyle.convention`).
- Use the same terms as the user-facing documentation and error messages.
- Examples in docstrings run as doctest examples, or are clearly not executable.

### Python generators

| Tool | Approach | Notes |
| --- | --- | --- |
| Sphinx with `autodoc` and `napoleon` | imports modules and renders docstrings into a Sphinx site | mature; `napoleon` reads Google and NumPy style |
| MkDocs with `mkdocstrings` (Python handler) | renders docstrings into MkDocs pages | static analysis by default, no import needed |
| pdoc | generates a standalone HTML API site | minimal configuration |

Whichever tool is used: build in CI with warnings as errors, generate from the
installed package (not a path hack), and do not commit generated HTML unless the
hosting requires it.

## Other ecosystems

- **TypeScript / JavaScript**: TSDoc or JSDoc comments, generated with TypeDoc
  or the framework's documentation tool. Enforce syntax with the matching
  ESLint plugin.
- **HTTP APIs**: the OpenAPI document is the reference. Generate it from the
  code (or the code from it), validate it in CI, and render it with a viewer.
  Every operation gets a summary, parameter descriptions, response schemas and
  error responses.
- **Command-line tools**: generate the reference from the argument parser's own
  help text so flags and defaults cannot drift.
- **Configuration files**: publish a JSON Schema with `description` for every
  key and generate the configuration reference from it.

## Review checklist

- Every public symbol has a summary line; changed behavior updated its
  docstring in the same change.
- Documented exceptions match what the code raises; documented defaults match
  the signature.
- Docstring examples run (or are marked illustrative).
- The generated reference builds without warnings, and a sample page was read
  to confirm rendering.
- No internal host names, credentials or personal data in examples.

## Sources

- [PEP 257: docstring conventions](https://peps.python.org/pep-0257/)
- [Google Python style guide: comments and docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- [Sphinx autodoc](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html)
- [Sphinx napoleon](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html)
- [mkdocstrings](https://mkdocstrings.github.io/)
- [pdoc](https://pdoc.dev/)
- [Python doctest](https://docs.python.org/3/library/doctest.html)
- [Ruff pydocstyle settings](https://docs.astral.sh/ruff/settings/#lint_pydocstyle_convention)
- [TSDoc](https://tsdoc.org/)
- [TypeDoc](https://typedoc.org/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [JSON Schema](https://json-schema.org/)
