# Component API design

## Building blocks

| Piece | Template |
| --- | --- |
| Button: typed variants, icon-only label enforcement, focusable pending state | [button.tsx](../assets/button.tsx.template) with [tests](../assets/button.test.tsx.template) |
| Dialog on native `<dialog>`: controlled, labelled, focus return | [dialog.tsx](../assets/dialog.tsx.template) with [tests](../assets/dialog.test.tsx.template) |
| Tokens: palette, semantic layer, dark mode, reduced motion, forced colors | [tokens.css](../assets/tokens.css.template) |
| Library public surface | [index.ts](../assets/ui-index.ts.template) |

Promotion, versioning, and documentation rules are in
[library governance](library-governance.md).

## Props

- Start from the native element's props (`ButtonHTMLAttributes`) and remove what
  the component controls. Consumers keep `id`, `data-*`, event handlers, and
  ARIA attributes they legitimately need.
- Name variants by intent (`primary`, `danger`), not appearance (`blue`).
- Use string unions instead of boolean flags. Three booleans give eight
  combinations, most of them meaningless.
- Encode required combinations in types: a discriminated union makes
  `aria-label` mandatory for icon-only buttons and forbidden when visible text
  already names the button.
- Mark props `Readonly`; never mutate them.
- Defaults live in the destructuring, so documentation and behavior agree.

## Refs

- React 19 passes `ref` as a regular prop for function components; declare
  `ref?: Ref<HTMLButtonElement>` and forward it to the DOM node.
- Libraries that still support React 18 use `forwardRef`; do not mix both styles
  in one library.
- Expose the DOM node, not an imperative handle, unless the component has real
  imperative operations (for example `focus()` on a composite widget, via
  `useImperativeHandle`).

## Composition over configuration

| Instead of | Prefer |
| --- | --- |
| `<Card title subtitle actions footer icon />` | `<Card><CardHeader>…</CardHeader><CardBody>…</CardBody></Card>` |
| `renderItem`, `renderEmpty`, `renderHeader` props everywhere | children and small slot components |
| A `type` prop that switches between unrelated layouts | separate components |
| Copying a primitive to change one style | a variant, or a `className` hook documented as supported |

Compound components share state through context created inside the library and
not exported.

## Controlled and uncontrolled state

- Value-holding components support both: `value` plus `onValueChange`
  (controlled) or `defaultValue` (uncontrolled). Switching modes during a
  component's lifetime is a bug; warn in development.
- Overlays (dialog, popover, menu) are controlled by `open` and `onClose` /
  `onOpenChange` so the owner decides when they close; Escape and backdrop
  clicks request closing through the callback.

## Polymorphism

- Avoid a generic `as` prop on interactive primitives: `<Button as="a">` produces
  links with button semantics or buttons with link semantics.
- Provide separate components (`Button`, `LinkButton`) that share styles. For
  layout primitives (`Stack`, `Box`), an `as` restricted to a small union of
  non-interactive elements is acceptable.

## Accessibility contract per component

Each primitive documents and tests:

1. Role and accessible name source.
2. Keyboard interactions (Tab, Enter, Space, arrows, Escape, Home/End where the
   ARIA pattern requires them).
3. Focus management: where focus goes on open, close, and removal.
4. States exposed to assistive technology (`aria-expanded`, `aria-pressed`,
   `aria-invalid`, `aria-busy`).
5. Minimum target size and visible focus in light, dark, and forced-colors modes.

Prefer native elements and platform features (`<dialog>`, `<details>`,
`popover` attribute, `<select>`) before hand-building an ARIA widget; native
behavior handles edge cases (focus, top layer, Escape) that custom code misses.

## Styling

- Components consume semantic tokens only; themes and dark mode replace token
  values, never component CSS.
- Use logical properties (`padding-inline`, `min-block-size`) for right-to-left
  support.
- Do not convey state with color alone; pair with text, icon, or shape.
- Respect `prefers-reduced-motion` through duration tokens.

## Anti-patterns

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| `<div onClick>` as a button | no keyboard, no role | `<button type="button">` |
| `disabled` on a pending submit button | focus lost, no announcement | `aria-disabled` plus `aria-busy` while pending |
| `isPrimary`, `isDanger`, `isSmall` booleans | invalid combinations | `variant` and `size` unions |
| Exporting internal parts "just in case" | every internal becomes public API | export only documented components |
| Fetching data inside a primitive | couples UI library to one backend | pass data in; features own fetching |
| Hard-coded colors in components | themes and dark mode break | semantic tokens |
| Custom modal with `div role="dialog"` and manual focus trap | inert background and top layer missing | native `<dialog>` with `showModal()` |

## Acceptance gates

- [ ] Props are typed so invalid combinations fail to compile, with a
      `@ts-expect-error` test proving it.
- [ ] The accessibility contract (role, name, keyboard, focus, states) is
      documented and tested.
- [ ] Components use semantic tokens and work in light, dark, forced-colors, and
      reduced-motion modes.
- [ ] Only documented components and prop types are exported.

## Sources

- React, `ref` as a prop: <https://react.dev/blog/2024/12/05/react-19#ref-as-a-prop>
- React, `useImperativeHandle`: <https://react.dev/reference/react/useImperativeHandle>
- MDN, `<dialog>`: <https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog>
- MDN, `popover` attribute: <https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/popover>
- WAI-ARIA Authoring Practices, patterns: <https://www.w3.org/WAI/ARIA/apg/patterns/>
- WAI-ARIA Authoring Practices, dialog (modal): <https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/>
- MDN, `forced-colors`: <https://developer.mozilla.org/en-US/docs/Web/CSS/@media/forced-colors>
- MDN, CSS logical properties: <https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_logical_properties_and_values>
- TypeScript, discriminated unions: <https://www.typescriptlang.org/docs/handbook/2/narrowing.html#discriminated-unions>
