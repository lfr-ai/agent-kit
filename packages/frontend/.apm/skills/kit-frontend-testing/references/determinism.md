# Determinism in frontend tests

A test is deterministic when the same code produces the same result on every
machine, in any order, at any time of day. Control every input the code reads.

## Inputs to control

| Input | Control |
| --- | --- |
| Timers (`setTimeout`, debounce, polling) | `vi.useFakeTimers()`; advance explicitly; restore in `afterEach` |
| Current date and time | `vi.setSystemTime(new Date("2026-01-15T10:00:00Z"))` with fake timers |
| Time zone and locale | set `TZ=UTC` in the test script; pass locale explicitly to formatters |
| Randomness and ids | inject a `random` or id generator (`newKey` props); seed or stub |
| Network | MSW with explicit handlers; unhandled requests fail |
| Response order | `respond.held` gates released in a chosen order |
| Storage | clear `localStorage`/`sessionStorage` after each test (setup does) |
| Module state | reset factories and singletons in `beforeEach` |
| Viewport and media queries | stub `matchMedia` per test when behavior depends on it |
| Environment variables | `vi.stubEnv` with `unstubEnvs: true` in config |

## Async discipline

- Await every `user-event` call.
- Use `findBy*` to wait for appearance; `waitFor` only for assertions that are not
  queries, and keep side effects out of its callback.
- With fake timers, wrap timer advances that trigger React updates in `act`.
- Do not mix real waiting with fake timers; `findBy` polls with timers too, so
  use `vi.advanceTimersByTimeAsync` when awaiting promises scheduled by timers.

## Races on purpose

To prove that an older response cannot overwrite a newer one:

1. Hold response A with a gate.
2. Trigger request B (change the filter) and let it resolve.
3. Release A.
4. Assert B's data is still shown and no error appears.

The same pattern proves that unmounting during a request does not update state
or move focus.

## Strict Mode in tests

Render with `<StrictMode>` in at least the tests of components with effects, or
enable it in the shared render helper, so double setup and cleanup in development
exposes missing cleanup.

## Order independence

- Run with `--sequence.shuffle` occasionally (or in CI on a schedule) to expose
  hidden coupling.
- Each test creates its own QueryClient, router, and data.
- `restoreMocks`, `unstubGlobals`, `unstubEnvs` in config undo per-test changes.

## Diagnosing a flaky unit test

1. Run it alone with `--repeat` style loops (`vitest run file -t name` in a shell
   loop) and with `--sequence.shuffle`.
2. Look for real time (`Date.now`, `new Date()`), unawaited promises, shared module
   state, and missing handlers.
3. Fix the source of nondeterminism; never add retries to unit tests.

## Acceptance gates

- [ ] No test reads the real clock, time zone, random source, or network.
- [ ] Race and unmount sequences are tested with explicit gates.
- [ ] Tests pass in shuffled order and in isolation.
- [ ] Effects are exercised under Strict Mode at least once.

## Sources

- Vitest, fake timers and dates: <https://vitest.dev/guide/mocking/dates>
- Vitest, `vi` API: <https://vitest.dev/api/vi>
- Vitest, CLI options (`--sequence.shuffle`): <https://vitest.dev/guide/cli>
- Testing Library, async methods: <https://testing-library.com/docs/dom-testing-library/api-async>
- Testing Library, user-event options (`advanceTimers`): <https://testing-library.com/docs/user-event/options>
- React, `StrictMode`: <https://react.dev/reference/react/StrictMode>
- MSW, `HttpResponse.error` and `delay`: <https://mswjs.io/docs/api>
