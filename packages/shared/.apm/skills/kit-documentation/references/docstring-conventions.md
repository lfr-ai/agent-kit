# Docstring conventions (Google style)

Docstrings document the contract a signature cannot express: meaning, units,
accepted values, errors, side effects and order of use. Types belong in
annotations. This page is the house style for Python; generating reference
pages from docstrings is covered in [API reference generation](api-reference.md).
Review date: 2026-10-23.

## Shape

```text
"""Summary line in one sentence, ending with a period.

Optional body: behavior, constraints, side effects, an example.

Args:
    name: Meaning, unit or format, and what None means.

Returns:
    What the value represents, including the empty case.

Raises:
    SpecificError: The condition under which it is raised.
"""
```

- Triple double quotes; the summary on the first line; a blank line before
  the body and before each section.
- Sections in this order when present: `Args`, `Returns` or `Yields`,
  `Raises`, `Example` or `Examples`, `Note`.
- Section items are indented four spaces; continuation lines four more.
- Inline code uses double backticks in Python docstrings (``like_this``) so
  reStructuredText-based generators render it; Markdown pages keep single
  backticks.

## What each part states

| Part | Write | Do not write |
| --- | --- | --- |
| Summary | what it does or returns, in the imperative or third person ("Return...", "Returns...") consistently | "This function..." or the function name again |
| Args | meaning, unit, range, format, default behavior when the default matters | the type already in the annotation |
| Returns | what the value means, empty or None results | "Returns: the result" |
| Yields | for generators: what each item is and when iteration stops | Returns for a generator |
| Raises | each exception a caller should handle, and when | exceptions that indicate bugs (`AssertionError`), or every exception a dependency might raise |
| Attributes | on classes and dataclasses: meaning of each public field | private fields |
| Example | short doctest for non-obvious calls | long tutorials |

`*args` and `**kwargs` are documented by their names without stars or with
them, consistently; describe what they forward to.

## Module, class and package docstrings

- **Module**: first line says what the module is for; the body lists the main
  entry points and any import-time constraints. Scripts document usage, inputs,
  outputs and exit codes.
- **Class**: what an instance represents and its invariants; constructor
  arguments go in the class docstring (`Args:`) or in `__init__`, consistently.
- **Dataclass and record**: an `Attributes:` section for public fields.
- **Package `__init__.py`**: what the package provides and its public API.
- **Property**: document like an attribute ("The invoice total in cents."),
  not like a method.

## What not to document

- Restated signatures, types, or the obvious ("Get the name." for `get_name`).
- Implementation narration ("loops over items and...") that will drift.
- History ("changed in March to fix...") - that belongs in version control.
- Private helpers whose name and signature already say everything; add a
  one-line summary only when the behavior is not obvious.
- Secrets, internal host names, personal data or ticket links that readers
  outside the team cannot open.

## Enforcement

- Ruff `D` rules with `convention = "google"` check presence and layout;
  `DOC` rules (pydoclint-style, where available) check that documented
  arguments and exceptions match the code.
- Review: a changed signature or new exception updates the docstring in the
  same change.
- Doctest examples run in the test suite or are clearly marked as not
  executable.

The [docstring template](../assets/docstrings.py.template) shows a module,
a record, a function, a generator and a class in this style.

## Primary sources

- [PEP 257: Docstring conventions](https://peps.python.org/pep-0257/)
- [Google Python Style Guide: comments and docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- Sphinx, [napoleon Google style example](https://www.sphinx-doc.org/en/master/usage/extensions/example_google.html)
- Ruff, [pydocstyle (D) rules](https://docs.astral.sh/ruff/rules/#pydocstyle-d) and [settings](https://docs.astral.sh/ruff/settings/#lint_pydocstyle_convention)
- Python, [doctest](https://docs.python.org/3/library/doctest.html)
