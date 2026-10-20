# Playwright patterns

Templates assume `@playwright/test` 1.4x or later and `@axe-core/playwright`.

## Building blocks

| Piece | Template |
| --- | --- |
| Config: projects, auth setup dependency, preview server, CI strictness | [playwright.config.ts](../assets/playwright.config.ts.template) |
| One-time sign-in with stored state | [auth.setup.ts](../assets/auth.setup.ts.template) |
| Page object with role-based locators | [orders.page.ts](../assets/orders.page.ts.template) |
| Fixtures: runtime-error guard, expected errors option, API failure helper | [fixtures.ts](../assets/fixtures.ts.template) |
| Journey spec: filters, back navigation, failure and retry, keyboard | [orders.spec.ts](../assets/orders.spec.ts.template) |
| Accessibility spec: axe scans, revealed states, focus visibility | [accessibility.spec.ts](../assets/accessibility.spec.ts.template) |

Flaky-test handling is in [flake triage](flake-triage.md).

## What belongs in a browser test

Browser tests are slow and expensive; reserve them for contracts only a real
browser proves:

- full journeys across routing, data loading, and persistence;
- real layout, focus, scrolling, and viewport behavior;
- browser APIs (storage, clipboard, file upload, downloads, service workers);
- cross-browser differences;
- accessibility scans of rendered pages.

Validation rules, formatting, and component state machines belong in unit and
component tests.

## Locators

Priority order, mirroring how users perceive the page:

1. `getByRole(role, { name })` for anything interactive or structural.
2. `getByLabel` for form controls, `getByPlaceholder` only if there is no label
   (which is itself a defect).
3. `getByText` for non-interactive content.
4. `getByTestId` for elements with no accessible semantics, as a deliberate
   contract.
5. CSS or XPath only for third-party markup you cannot change.

Scope locators (`list.getByRole("listitem").filter({ hasText })`) instead of
using `nth()`. A locator that needs an index usually signals a missing accessible
name.

## Waiting and assertions

- Use web-first assertions (`await expect(locator).toBeVisible()`); they retry
  until the timeout. Never `waitForTimeout`.
- Assert the user-visible outcome first, then URL or persisted state when it is
  part of the contract (`toHaveURL`).
- `expect.poll` for values outside the DOM (an API read-back); `toPass` for a
  block of steps that must eventually succeed.
- Avoid `page.waitForLoadState("networkidle")`: long-polling, analytics, and
  live connections keep the network busy.

## Isolation and data

- Each test gets a fresh browser context: cookies, storage, and cache are
  isolated by default. Do not share pages between tests.
- Authenticate once in a setup project and reuse `storageState`; use one
  account per parallel worker when tests mutate account-level data.
- Create test data through an API fixture with unique names
  (`ORD-${testInfo.workerIndex}-${Date.now()}`) and delete it in teardown, or run
  against a disposable environment that is reset per run.
- Never depend on a live production account or data that other people change.

## Network control

- `page.route(pattern, handler)` fakes external boundaries: third-party APIs,
  rare failure statuses, slow responses. Keep the application's own client,
  parsing, and rendering real.
- Prefer `route.fallback()` for pass-through so later handlers and the real
  network still apply.
- `page.routeFromHAR` replays recorded responses for deterministic visual tests;
  scrub secrets from HAR files before committing them.
- Simulate offline with `context.setOffline(true)`; simulate latency with a
  delayed `route.fulfill` rather than CPU throttling.

## Evidence on failure

- `trace: "on-first-retry"` keeps CI fast and still captures a trace for any
  retried failure. Open with `npx playwright show-trace`.
- Screenshots and video only on failure; they can contain personal data, so test
  accounts use synthetic data and artifacts have a retention limit.
- Attach diagnostic text with `testInfo.attach` instead of `console.log`.

## CI

- `forbidOnly` in CI, bounded retries (1 or 2), report retries as flaky rather
  than passed.
- Install browsers with `npx playwright install --with-deps` in the CI image, or
  use the official Playwright container image pinned to the package version.
- Shard large suites (`--shard=1/4`) and merge reports with `merge-reports`.
- Run against a production build (`vite build` plus `preview`), not the dev server.

## Anti-patterns

| Anti-pattern | Fix |
| --- | --- |
| `page.waitForTimeout(2000)` | assert the awaited state |
| `locator("div > span:nth-child(3)")` | role and name locator |
| Logging in through the UI in every test | setup project and `storageState` |
| Test B relies on data created by test A | each test creates or seeds its own data |
| Mocking the application's own API in every test | mock only external services and rare failures |
| Retries set to 5 to get green builds | triage flakes; fix the race |
| `expect(await locator.isVisible()).toBe(true)` | `await expect(locator).toBeVisible()` (retries) |

## Acceptance gates

- [ ] Each spec covers one journey with a visible outcome and at least one
      failure or recovery path.
- [ ] Locators are role or label based; any test id is a documented contract.
- [ ] No fixed sleeps; runtime errors fail the test unless explicitly expected.
- [ ] Data is isolated per test; the suite passes with `--repeat-each=3` and in
      parallel.
- [ ] Executed browsers, commands, and results are reported; unexecuted plans are
      labeled as plans.

## Sources

- Playwright, best practices: <https://playwright.dev/docs/best-practices>
- Playwright, locators: <https://playwright.dev/docs/locators>
- Playwright, assertions: <https://playwright.dev/docs/test-assertions>
- Playwright, authentication: <https://playwright.dev/docs/auth>
- Playwright, fixtures: <https://playwright.dev/docs/test-fixtures>
- Playwright, network: <https://playwright.dev/docs/network>
- Playwright, trace viewer: <https://playwright.dev/docs/trace-viewer>
- Playwright, continuous integration: <https://playwright.dev/docs/ci>
- Playwright, accessibility testing: <https://playwright.dev/docs/accessibility-testing>
- Playwright, web server: <https://playwright.dev/docs/test-webserver>
