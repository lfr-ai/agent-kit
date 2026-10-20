# Library governance

## Promotion criteria

Promote a component into the shared library only when all are true:

1. At least two features need the same behavior now (not hypothetically).
2. The behavior can be described without feature vocabulary.
3. An owner accepts maintenance, review, and migration duties.
4. The accessibility contract and keyboard behavior are defined.

Until then, keep the component inside its feature and export it from the
feature's public index if another feature needs it temporarily.

## Change classification

| Change | Class | Required steps |
| --- | --- | --- |
| New optional prop with a backward-compatible default | minor | tests, docs |
| New variant value | minor | visual check in every theme |
| Visual change to an existing variant | minor or major by impact | screenshot review, consumer notice |
| Renamed or removed prop, changed default, changed DOM structure that consumers style or test | major | deprecation period, codemod or migration notes |
| Changed keyboard or focus behavior | major | accessibility review, consumer notice |

In a monorepo without versions, a "major" change means: update every consumer in
the same change, or add the new API beside the old one and migrate in steps.

## Deprecation

1. Add the replacement and mark the old prop or component deprecated in its type
   (`/** @deprecated Use variant="danger". */`) so editors flag usages.
2. Optionally warn once in development builds.
3. Migrate consumers; track remaining usages with a code search.
4. Remove after the announced period.

## Documentation per component

- Purpose and when not to use it.
- Props table generated from types, with defaults.
- Accessibility contract: role, name, keyboard, focus, states.
- Examples of each variant and state, including pending, disabled, error, long
  text, and right-to-left.
- Do and do not examples for content (button labels, dialog titles).

If the project uses a component workshop (for example Storybook), each state is a
story and doubles as a visual and accessibility test target; otherwise keep a
plain example page rendered in browser tests.

## Quality gates in CI

- Type check and unit tests for every primitive.
- Accessibility assertions in component tests (roles, names, focus) and axe
  scans on rendered examples in a real browser.
- Visual regression screenshots for each variant in light and dark themes.
- Bundle size budget for the library entry point; flag new dependencies.

## Dependency policy

- Prefer platform features and existing dependencies.
- A headless behavior library (focus management, positioning) is acceptable when
  it replaces substantial hand-written ARIA logic and is maintained; wrap it so
  consumers depend on the library's API, not the third party's.
- Never add a dependency for a one-off wrapper.

## Acceptance gates

- [ ] Promotion criteria met and recorded in the component contract.
- [ ] Change classified; major changes include migration of all consumers or a
      deprecation path.
- [ ] Documentation lists purpose, props, accessibility contract, and states.
- [ ] CI covers types, behavior, accessibility, and visual regressions.

## Sources

- Semantic Versioning: <https://semver.org/>
- TypeScript, JSDoc `@deprecated`: <https://www.typescriptlang.org/docs/handbook/jsdoc-supported-types.html#deprecated>
- Storybook, accessibility tests: <https://storybook.js.org/docs/writing-tests/accessibility-testing>
- Playwright, visual comparisons: <https://playwright.dev/docs/test-snapshots>
- WAI, accessibility in design systems (Getting started): <https://www.w3.org/WAI/design-develop/>
