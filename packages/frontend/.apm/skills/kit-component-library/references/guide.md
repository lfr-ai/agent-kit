# Reusable primitive API and adoption gates

## Verification prerequisites

- Locate the current primitive, design tokens, exports, two real consumers, and
  installed component/visual test tools. With only one use case, prefer a local
  feature component unless the repository already requires a shared primitive.
- Record the framework and version actually in use. React examples or typings
  are relevant only to React consumers; no new dependency is implied.
- Identify the native HTML element or established accessible widget pattern.
  Existing primitive behavior is a compatibility contract, not disposable detail.

## API quality gates

| Decision | Acceptance gate |
| --- | --- |
| Semantic purpose | Name describes one task; element, role, accessible name, and keyboard behavior agree. |
| States | Default, disabled, pending, invalid, selected/expanded where applicable, and focus states have explicit behavior. |
| Prop design | Reject impossible combinations through existing types or boundary validation; avoid booleans encoding unrelated modes. |
| Ownership | Controlled and uncontrolled modes have documented defaults/events; a mounted instance does not silently switch modes. |
| Composition | Consumers can provide content/labels without importing internals; styling uses existing tokens rather than parallel values. |
| Boundary | No feature-specific authorization, transport calls, analytics destination, or entity policy in the primitive. |
| Compatibility | Existing consumers keep event, focus, label association, DOM semantics and form behavior unless a migration is intentional. |

Forward applicable native attributes, accessibility relationships, and refs using
the repository's established pattern. A wrapper that swallows `id`, `name`,
`type`, `disabled`, or label/description relationships can silently break forms.
A button inside a form must have an intentional submit/non-submit type.

## Failure modes and negative cases

- Render two instances with independent labels/descriptions: generated IDs cannot
  collide and one instance's state must not affect the other.
- Supply a long translated label and large text at a narrow viewport: controls
  remain operable, focus outlines visible, and hit targets usable.
- Activate disabled/pending and invalid variants using keyboard and pointer:
  behavior matches semantics; do not rely on muted colors alone.
- Remove a focused item or close an overlay: focus lands on a defined surviving
  target, not an unmounted ref.
- Exercise controlled updates, uncontrolled defaults, and prohibited prop
  combinations. Do not keep an internal mirror that overrides the consumer.
- Consume through the public export in a real feature; an isolated story can miss
  CSS collisions, form submission, localization, or provider assumptions.

## Adoption, recovery and verification

1. Fill the [component contract](../assets/component-contract.md), including
   counterexamples that should remain feature-local.
2. Implement the smallest API serving the evidenced consumers. Keep old exports
   until their callers are migrated; do not broaden adoption during diagnosis.
3. Run existing type checks, focused component interaction tests, and a consuming
   feature test. Check responsive/focus behavior in a browser when available.
4. If adoption reveals a hidden dependency, first localize that behavior back to
   the feature or retain a compatibility adapter; avoid a new universal mode flag.
5. For a breaking change, document old-to-new usage and verify both consumers.
   Revert the bounded migration if semantics or focus cannot yet be preserved.

Snapshots and generated stories alone do not establish keyboard usability.
Record untested consumer variants explicitly instead of widening the public API
on assumed compatibility.

## Primary official sources

- HTML interactive elements and semantics: <https://html.spec.whatwg.org/multipage/interactive-elements.html>
- ARIA APG design patterns: <https://www.w3.org/WAI/ARIA/apg/patterns/>
- TypeScript narrowing and discriminated unions: <https://www.typescriptlang.org/docs/handbook/2/narrowing.html>
- React state ownership, when applicable: <https://react.dev/learn/sharing-state-between-components>
