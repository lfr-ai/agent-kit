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
   update docstrings in the same change as the code.
5. Record decisions with lasting consequences in a decision record from the
   [ADR template](assets/adr.md.template); never rewrite an accepted record,
   supersede it.
6. Keep root files short; start a missing README from the
   [README template](assets/README.md.template).
7. Add a user-facing entry to the changelog following
   [Keep a Changelog](references/changelog.md), starting a missing file from the
   [changelog template](assets/CHANGELOG.md.template).
8. Use exact product and configuration terms from the implementation, and
   synthetic examples only: no secrets, private endpoints or personal data.
9. Remove or supersede guidance the change made false, including examples on
   other pages.
10. Run the repository's documentation checks following
    [docs as code](references/docs-as-code.md): lint, spelling, links, build
    with warnings as errors, and doctest examples where configured.
11. State which pages changed and the exact checks performed; label commands
    that were not executed as illustrative.

The [reader checks](references/guide.md) apply to every page.

## Acceptance gates

- Each changed page has one Diataxis kind and a title that states what the
  reader gets.
- Commands were run in the declared environment or are labeled illustrative;
  defaults and errors match the implementation and tests.
- Generated reference builds without warnings; docstrings of changed public
  symbols were updated.
- The changelog has an entry for every user-visible change, in the right
  category, with breaking changes stated plainly.
- Lint, spelling and local link checks pass; no page contradicts another.
