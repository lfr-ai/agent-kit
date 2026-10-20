# Test layers and component testing patterns

Templates assume Vitest 3 or later, Testing Library for React, `user-event` 14,
and MSW 2.

## Building blocks

| Piece | Template |
| --- | --- |
| Vitest config merged with Vite config, coverage thresholds | [vitest.config.ts](../assets/vitest.config.ts.template) |
| Setup: matchers, cleanup, runtime config, `matchMedia`, act guard | [setup.ts](../assets/test-setup.ts.template) |
| Render helper with QueryClient, memory router, user-event | [render-with-providers.tsx](../assets/render-with-providers.tsx.template) |
| MSW lifecycle and handler builders (held, slow, error) | [msw.ts](../assets/msw.ts.template) |
| Test data builder | [order.factory.ts](../assets/order.factory.ts.template) |
| Fake-timer example | [debounced-search.tsx](../assets/debounced-search.tsx.template), [test](../assets/debounced-search.test.tsx.template) |

Determinism rules are in [determinism](determinism.md).

## Choosing the layer

| Behavior | Cheapest proving layer | Tooling |
| --- | --- | --- |
| Formatting, mapping, schema rules, reducers | unit | Vitest, no DOM |
| Hook with cache or timers | hook test | `renderHook` with providers |
| Component states, user interaction, accessible names, focus | component | Testing Library, `user-event`, MSW |
| Route loaders, redirects, boundaries, URL state | route integration | memory router with real route objects |
| Layout, real focus rings, scrolling, browser APIs, cross-browser | browser | Playwright |
| Visual regressions | browser screenshots | Playwright `toHaveScreenshot` |
| Contract with the real API | contract or end-to-end in a test environment | provider-verified contract or Playwright |

Write the test at the lowest layer that would fail if the behavior broke. Add a
browser test only when a lower layer cannot observe the failure.

## Query priority

1. `getByRole` with `name`: buttons, links, headings, form controls, regions.
2. `getByLabelText`: form fields.
3. `getByPlaceholderText`: only when no label exists (and file a defect).
4. `getByText`: non-interactive content.
5. `getByDisplayValue`: current values of filled fields.
6. `getByAltText`, `getByTitle`: images and titled elements.
7. `getByTestId`: last resort, documented.

Variants: `getBy` (must exist now), `queryBy` (assert absence), `findBy` (wait
for appearance). Use `within(region)` to scope.

## Interactions

- `const user = userEvent.setup()` once per test, before rendering; await every
  call.
- Prefer `user.type`, `user.click`, `user.keyboard("{Enter}")`, `user.tab()` over
  `fireEvent`; they dispatch the full event sequence a browser would.
- With fake timers pass `advanceTimers: vi.advanceTimersByTime` to `setup`, and
  keep the `jest` clock bridge from the [test setup](../assets/test-setup.ts.template):
  without it every `user.*` call hangs under `vi.useFakeTimers()`.

## Assertions that matter

| Prefer | Over |
| --- | --- |
| `toBeVisible()`, `toHaveTextContent()` | snapshot of the whole tree |
| `toHaveAccessibleName()`, `toHaveAccessibleDescription()` | checking `aria-*` attributes one by one |
| `toHaveFocus()` after an action | assuming focus moved |
| `toBeDisabled()` / `toHaveAttribute("aria-invalid", "true")` | class names |
| request assertions in the MSW handler (body, query) | spying on the API module |
| `expect(onSave).toHaveBeenCalledWith(...)` for callback contracts | counting renders or hook calls |

## Network boundary

- Fake HTTP with MSW, not by mocking the API module or `fetch`. The real client,
  schemas, and query options run, so contract drift shows up in tests.
- `onUnhandledRequest: "error"` turns a missing handler into a failing test.
- One server per test file through `useMswServer`; override per test with
  `server.use(...)`; `resetHandlers` after each test.
- Use `respond.held` to keep a request pending and assert loading UI or race
  ordering deterministically.

## Coverage gates

- Thresholds in `vitest.config.ts` guard against large untested additions; they
  are a floor, not a goal. Do not add assertion-free tests to meet them.
- Review uncovered branches in changed files (`--coverage.include` on the touched
  paths) and decide whether each is reachable.
- Mutation-style check for a new regression test: revert the fix locally, confirm
  the test fails, restore the fix.

## Anti-patterns

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| `container.querySelector(".btn-primary")` | tied to markup, ignores accessibility | `getByRole("button", { name })` |
| `vi.mock("../api/orders.api")` everywhere | schema and client never tested | MSW at the HTTP boundary |
| Snapshot of an entire page | brittle, approved without reading | targeted assertions |
| `await new Promise(r => setTimeout(r, 500))` | slow and flaky | `findBy*`, `waitFor`, fake timers |
| `waitFor(() => { click(); expect(...) })` | side effects repeated on retry | act outside, assert inside `waitFor` |
| Shared QueryClient across tests | cached data leaks between tests | new client per test |
| Testing hook internals (`useState` calls) | breaks on refactor | test visible behavior |
| `act()` sprinkled to silence warnings | hides unawaited updates | await the interaction or `findBy` |

## Acceptance gates

- [ ] Each behavior is tested at the cheapest layer that can observe its failure.
- [ ] Queries use roles and labels; any test id is justified.
- [ ] The network is faked at HTTP level with unhandled requests failing.
- [ ] New regression tests were seen failing without the fix.
- [ ] Type check, lint, and the focused test command pass with output recorded.

## Sources

- Testing Library, guiding principles: <https://testing-library.com/docs/guiding-principles>
- Testing Library, query priority: <https://testing-library.com/docs/queries/about#priority>
- Testing Library, user-event: <https://testing-library.com/docs/user-event/intro>
- jest-dom matchers: <https://github.com/testing-library/jest-dom>
- Vitest, configuration: <https://vitest.dev/config/>
- Vitest, coverage: <https://vitest.dev/guide/coverage>
- Vitest, mocking timers: <https://vitest.dev/guide/mocking/timers>
- MSW, Node integration: <https://mswjs.io/docs/integrations/node>
- MSW, best practices: <https://mswjs.io/docs/best-practices>
- React, `act`: <https://react.dev/reference/react/act>
