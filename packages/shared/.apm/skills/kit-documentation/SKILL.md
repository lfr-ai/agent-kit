---
name: kit-documentation
description: Use when updating documentation for changed behavior, setup, supported scope, or failure handling.
license: MIT
---

# Document the user-visible contract

## Procedure

1. Identify the reader, the decision or task they face, and the owning page.
   Read the repository's documentation conventions and nearby pages first.
2. Classify the change with [Diataxis](references/diataxis.md): tutorial,
   how-to guide, reference or explanation. Put each piece in a page of the
   matching kind and link between kinds instead of mixing them.
3. Describe observable behavior, prerequisites, defaults, errors and recovery.
   For task pages use the [procedure template](assets/procedure.md.template).
4. Generate reference material from the source (docstrings, schemas, argument
   parsers, OpenAPI) as in [API reference generation](references/api-reference.md);
   update docstrings in the same change as the code, following the
   [docstring conventions](references/docstring-conventions.md) and the
   [docstring template](assets/docstrings.py.template).
5. Add a diagram only when it answers a structural or sequence question better
   than prose; follow [Mermaid diagrams](references/mermaid-diagrams.md), start
   from the [diagram templates](assets/diagrams.md.template), keep it under
   about 30 nodes, and render it once with the Mermaid CLI.
6. Record decisions with lasting consequences as a decision record from the
   `kit-project-memory` skill's MADR-style template; never rewrite an accepted
   record, supersede it.
7. Keep root files short; start a missing README from the
   [README template](assets/README.md.template).
8. Add a user-facing entry to the changelog following
   [Keep a Changelog](references/changelog.md), starting a missing file from the
   [changelog template](assets/CHANGELOG.md.template).
9. Use exact product and configuration terms from the implementation, and
   synthetic examples only: no secrets, private endpoints or personal data.
10. Remove or supersede guidance the change made false, including examples on
    other pages.
11. Run the repository's documentation checks following
    [docs as code](references/docs-as-code.md): lint, spelling, links, build
    with warnings as errors, and doctest examples where configured.
12. State which pages changed and the exact checks performed; label commands
    that were not executed as illustrative.

The [reader checks](references/guide.md) apply to every page.

## Acceptance gates

- Each changed page has one Diataxis kind and a title that states what the
  reader gets.
- Commands were run in the declared environment or are labeled illustrative;
  defaults and errors match the implementation and tests.
- Generated reference builds without warnings; docstrings of changed public
  symbols were updated.
- Every diagram answers one stated question, stays under about 30 nodes,
  uses names from the code and renders without errors.
- The changelog has an entry for every user-visible change, in the right
  category, with breaking changes stated plainly.
- Lint, spelling and local link checks pass; no page contradicts another.
