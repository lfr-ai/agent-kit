# Visual regression testing

Screenshot comparison catches unintended visual changes; it does not tell whether
a design is good. Use it to protect reviewed states after a human approved them.

## Setup

- Use Playwright `toHaveScreenshot`; the
  [visual spec template](../assets/orders.visual.spec.ts.template) covers states,
  viewports, and dark theme.
- Baselines depend on OS, fonts, and browser build. Generate and compare them in
  the same container image in CI; never commit baselines produced on a different
  platform.
- Stub network data with fixed fixtures; freeze time (`page.clock`) and locale.
- Disable animations (`animations: "disabled"` in the config) and caret blinking.
- Mask volatile regions (timestamps, avatars, ads) with `mask`, or mark them
  `data-dynamic` and mask by selector.

## What to capture

| Capture | Why |
| --- | --- |
| Each state of a key screen (loading skeleton, empty, populated, error) | states regress independently |
| Narrow and desktop viewports | breakpoints break separately |
| Light and dark themes | token changes affect themes differently |
| Component examples in isolation | small diffs, fast triage |
| Full page only where layout across sections matters | full-page diffs are noisy |

Avoid capturing every page at every viewport: the suite becomes slow and diffs are
approved without reading.

## Thresholds

- Start strict (`maxDiffPixelRatio` around 0.01 or `maxDiffPixels` small).
- Loosen per test only with a recorded reason (for example font anti-aliasing on
  one browser).
- A flaky screenshot is a determinism bug: find the moving part.

## Updating baselines

1. Make the intended visual change.
2. Run `npx playwright test --update-snapshots` in the CI image (or the
   project's documented update job).
3. Review every changed image in the diff viewer; reject unexpected changes.
4. Commit baselines with the code change and mention them in the review.

## Acceptance gates

- [ ] Baselines generated in the CI environment and committed with the change.
- [ ] Data, time, locale, and animations are fixed; volatile regions masked.
- [ ] Every updated baseline was reviewed image by image.
- [ ] Visual tests complement, not replace, the state and interaction review.

## Sources

- Playwright, visual comparisons: <https://playwright.dev/docs/test-snapshots>
- Playwright, `toHaveScreenshot` options: <https://playwright.dev/docs/api/class-pageassertions#page-assertions-to-have-screenshot-1>
- Playwright, clock: <https://playwright.dev/docs/clock>
- Playwright, Docker images: <https://playwright.dev/docs/docker>
