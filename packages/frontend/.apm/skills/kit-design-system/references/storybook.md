# Storybook stories, tests, and visual review

Reviewed 2026-10-23 against Storybook 10.6 documentation. Storybook 9 moved
essentials and the test utilities into the core package (`storybook/test`);
Storybook 10 is ESM-only. Check the installed major before copying imports.

## What a story is for

| Need | Story feature |
| --- | --- |
| Show one variant or state | A named CSF3 story object with `args` |
| Explore props interactively | `argTypes` with controls; `args` defaults on `meta` |
| Prove behavior | `play` function with `userEvent` and `expect` |
| Catch accessibility violations | `@storybook/addon-a11y` with `parameters.a11y.test` |
| Run stories as tests in CI | `@storybook/addon-vitest` (Vitest browser mode) or the test runner |
| Generate reference docs | `tags: ["autodocs"]` plus JSDoc on props; MDX for usage guidance |
| Catch visual drift | One of the visual regression options below |

## CSF3 rules

- Default export `meta` typed with `satisfies Meta<typeof Component>`; each
  named export is a story typed `StoryObj<typeof meta>`.
- Put shared defaults in `meta.args`; stories override only what differs.
- Use `fn()` from `storybook/test` for callback args so calls are asserted
  and shown in the actions panel.
- One story per meaningful state: default, each variant, size, disabled,
  pending, long text, error, empty, and right-to-left when supported.
- Wrap providers (theme, router, query client) in `preview` decorators, not
  inside each story. Mock network with MSW handlers in `parameters`.
- Keep stories deterministic: fixed dates, seeded data, no live endpoints.

## Interaction and accessibility tests

- Query by role and accessible name inside `play`; assert visible results and
  callback calls, the same way component tests do (see `kit-frontend-testing`).
- Set `parameters.a11y.test` to `"error"` globally; downgrade a single story
  to `"todo"` only with a linked follow-up.
- Axe finds a subset of issues. Keyboard order, focus return, and
  screen-reader wording still need the `kit-accessibility` procedure.
- Stories are not a substitute for component tests of complex logic; keep
  logic tests in Vitest and use stories for rendered states and documentation.

## Visual regression options

| Option | Strengths | Costs |
| --- | --- | --- |
| Hosted visual testing service | Cross-browser capture, review UI, baselines per branch | External service, data leaves the build; needs approval |
| Playwright screenshots of story iframes | Local, versioned baselines, no extra service | Font and OS rendering noise; pin the browser image |
| No pixel baselines | Zero maintenance | Relies on reviewers and interaction tests |

Pin fonts, disable animations, and capture in a fixed container image.
Review every changed image; never bulk-accept baselines. Threshold and
baseline policy live in the `kit-ui-review` skill.

## Documentation

- Autodocs page per component: purpose, when not to use it, variants, tokens
  consumed, accessibility contract, and a link to the source.
- Document tokens in a dedicated page that renders swatches from the CSS
  variables themselves, so the page cannot drift from the theme file.
- Publish the static Storybook only from CI; it is public if hosted publicly.

## Failure modes

| Symptom | Cause | Repair |
| --- | --- | --- |
| Story passes, app breaks | Story bypasses real providers | Shared decorators mirroring app providers |
| Flaky play function | Fixed delays or real timers | `findBy*` queries; fake time in loaders |
| Axe clean, keyboard broken | Automated scan only | Manual keyboard pass per state |
| Visual diffs on every run | Unpinned fonts, animations | Pin environment; reduce motion |
| Docs drift | Hand-written prop tables | Autodocs from types and JSDoc |

## Primary sources

- Writing stories (CSF): <https://storybook.js.org/docs/writing-stories>
- Args: <https://storybook.js.org/docs/writing-stories/args>
- Interaction tests: <https://storybook.js.org/docs/writing-tests/interaction-testing>
- Accessibility tests: <https://storybook.js.org/docs/writing-tests/accessibility-testing>
- Vitest addon: <https://storybook.js.org/docs/writing-tests/integrations/vitest-addon>
- Visual tests: <https://storybook.js.org/docs/writing-tests/visual-testing>
- Autodocs: <https://storybook.js.org/docs/writing-docs/autodocs>
- Main configuration: <https://storybook.js.org/docs/configure>
- Playwright visual comparisons: <https://playwright.dev/docs/test-snapshots>
