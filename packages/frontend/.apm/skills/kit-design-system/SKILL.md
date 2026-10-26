---
name: kit-design-system
description: Use when defining design tokens, Tailwind v4 themes, dark mode, shadcn/ui theming, variants or Storybook docs.
license: MIT
---

# Run the design system from tokens

## Resources

- [Token and theming guide](references/guide.md): token layers, Tailwind v4
  `@theme`, dark mode, shadcn/ui ownership, variants, contrast, failure modes.
- [Storybook and visual review](references/storybook.md): CSF3 stories, args,
  interaction and accessibility tests, visual regression choices, docs.
- [Token review worksheet](assets/token-review.md.template) to fill per change.
- Templates: [theme tokens](assets/theme.css.template),
  [variant component](assets/button-variants.tsx.template) with
  [tests](assets/button-variants.test.tsx.template),
  [CSF3 story](assets/button.stories.tsx.template),
  [Storybook main](assets/storybook-main.ts.template) and
  [preview](assets/storybook-preview.tsx.template).
- Checker: [hard-coded value scan](assets/check_design_tokens.py)
  (`PATHS`, `--token-file`, `--allow-px`, `--suffix`).
- Related owners: component APIs and promotion in `kit-component-library`,
  contrast and keyboard checks in `kit-accessibility`, screenshot review in
  `kit-ui-review`, Vite and Bun setup in `kit-frontend-build`.

## Procedure

1. Read the guide; fill the token review worksheet for the proposed change.
2. Inspect the installed Tailwind, shadcn/ui, and Storybook versions and the
   existing token file; extend it instead of starting a second system.
3. Keep three layers: raw palette, semantic roles (surface, text, action,
   border, status, focus), and component tokens only where a component needs
   an independent dial.
4. Declare utility-generating tokens in one CSS `@theme` block; keep runtime
   theme values in `:root` and `.dark` and map them with `@theme inline`. Add a
   JavaScript Tailwind config only for a plugin that has no CSS-first form.
5. Define dark mode by overriding semantic variables, not by duplicating
   component classes; choose the class or media strategy once.
6. Treat copied shadcn/ui components as owned source: review, test, and adapt
   them to the semantic tokens; record the upstream revision for later diffs.
7. Express visual variants with `class-variance-authority`; type variant props
   from the definition and set `defaultVariants`.
8. Check contrast for every semantic text and boundary pair in light and dark
   themes, plus forced colors and reduced motion.
9. Write CSF3 stories for each variant and state; add `play` interaction tests
   and the accessibility addon; choose a visual regression method deliberately.
10. Run the hard-coded value scan on changed `.tsx` and `.css` files; replace
    findings with tokens or record a justified exception.
11. Document token names, intent, and usage rules in the component docs page.
12. Report which builds, story tests, contrast, and visual checks actually ran.

## Acceptance gates

- [ ] Tokens live in one theme file with palette, semantic, and component layers.
- [ ] Components use semantic tokens only; the scan reports no new findings.
- [ ] Light, dark, and forced-colors contrast pairs meet WCAG 2.2 AA.
- [ ] Every variant and state has a story; interaction and axe checks pass.
- [ ] Copied shadcn/ui components are tested and recorded with their origin.
- [ ] Visual baselines (if used) were reviewed image by image.
