---
name: kit-component-library
description: Use when creating or changing reusable UI primitives, design tokens, or shared component APIs.
license: MIT
---

# Keep shared components purposeful

## Resources

- [Primitive design guide](references/guide.md): invalid combinations, focus
  lifecycle, migration recovery.
- [Component API design](references/component-api.md): props, refs, composition,
  controlled state, polymorphism, accessibility contract, styling, anti-patterns.
- [Library governance](references/library-governance.md): promotion criteria,
  change classes, deprecation, documentation, CI gates, dependencies.
- [Component contract](assets/component-contract.md) to fill per component.
- Templates: [button](assets/button.tsx.template) with
  [tests](assets/button.test.tsx.template),
  [dialog](assets/dialog.tsx.template) with [tests](assets/dialog.test.tsx.template),
  [design tokens](assets/tokens.css.template),
  [library index](assets/ui-index.ts.template).

## Procedure

1. Read the guide; fill the component contract for the proposed public API.
2. Confirm at least two real use cases need the same behavior before promoting.
3. Define purpose, supported states, accessibility contract, and non-goals.
4. Prefer native elements and platform features; compose instead of adding
   boolean mode props.
5. Reuse existing tokens and primitives; no parallel color or spacing system.
6. Keep feature policy and data fetching out of generic UI components.
7. Make controlled versus uncontrolled behavior explicit and consistent.
8. Type props so invalid combinations fail to compile; prove it with
   `@ts-expect-error` tests.
9. Test semantics, keyboard behavior, focus lifecycle, and state variants, plus
   one consuming feature.
10. Check light, dark, forced-colors, reduced-motion, narrow, and wide views.
11. Classify the change; provide deprecation or migration for breaking changes.
12. Export only documented components; avoid dependencies for one-off wrappers.
    Report which consuming and browser checks actually ran.

## Acceptance gates

- [ ] Promotion criteria and the accessibility contract are recorded.
- [ ] Type-level tests reject invalid prop combinations.
- [ ] Keyboard, focus, and state tests pass; native semantics are preserved.
- [ ] Semantic tokens only; themes and forced colors verified.
- [ ] Breaking changes migrate consumers or follow a deprecation path.
