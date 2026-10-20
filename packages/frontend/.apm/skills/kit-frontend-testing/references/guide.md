# Frontend test ownership and determinism

## Verification prerequisites

- Inspect the existing package scripts, runner/version, DOM environment, test
  providers, network mocks, and fixture/reset conventions. Do not assume Jest,
  Vitest, React Testing Library, or a browser runner is installed.
- Write an observable behavior before choosing a layer. Identify which boundary
  must be real for that assertion to be meaningful.
- Obtain minimal synthetic success, pending, empty, denied, malformed and failed
  inputs. If an environment is unavailable, separate authored tests from executed
  evidence and record the missing prerequisite.

## Layer selection and quality gates

| Contract | Cheapest adequate layer | Required assertion |
| --- | --- | --- |
| Parsing, formatting, reducer transition | Pure unit | Boundary input produces exact valid output or explicit rejection; no mutation of input. |
| Control behavior, validation, focus, pending UI | Component | User interaction changes visible semantics/state and preserves keyboard access. |
| Adapter, query cache, route loader integration | Integration | Real parsing/state transitions respond to transport results and races. |
| Direct navigation, native browser behavior, cross-layer journey | Browser | Real rendered journey completes, including URL/focus/persistence if promised. |

One contract can have several risks, but avoid repeating the entire happy path
at every layer. A component test in DOM emulation cannot verify layout, actual
navigation, screen-reader output, or cross-browser behavior.

## Assertion design

- Prefer roles and accessible names, then visible labels/text. Use implementation
  selectors only when no semantic query identifies a legitimate noninteractive
  target. Do not add ARIA solely to make tests easier.
- Exercise realistic input/keyboard sequences using existing helpers. Assert
  rendered feedback, focus and enabled/disabled state, not internal hook counts.
- Intercept transport rather than replacing the parser, cache, and UI all at
  once. A test that mocks the unit whose behavior it claims to prove is circular.
- Keep asynchronous assertions awaited and place side effects outside retrying
  assertion callbacks. A missing `await` can produce a false pass.
- Make pending observable by holding a controlled response unresolved; finish or
  cancel it in cleanup. Avoid arbitrary sleeps or waiting for incidental effects.

## Negative cases and failure modes

1. Complete newer request B before older A. The UI must keep B's result; include
   malformed and rejected outcomes at the adapter boundary.
2. Fail once then retry. The error must be readable and recoverable without
   duplicate requests or stale error messages.
3. Return an empty collection instead of `null`, then the contract's missing
   value. Verify intentional differences rather than accidental truthiness.
4. Unmount while pending or advance a retry timer after disposal. No owned
   listener/timer or late update survives.
5. Run the test alone and beside a neighboring test. Restore mocks, clock mode,
   storage, handlers and fixtures so order cannot change results.
6. Check invalid input and keyboard activation. A screenshot/snapshot cannot
   establish validation logic or focus behavior.

## Recovery and verification

- For a defect, first demonstrate the new test fails for the intended observable
  reason. For existing behavior, use a safe local fault probe only if permitted;
  never weaken an assertion just to obtain green output.
- On flakiness, capture the first failure and identify clock, data, ordering or
  cleanup leakage. Fix the unstable boundary rather than increasing all timeouts.
- Run the smallest affected selectors in one command, then a neighboring
  integration case when the shared seam changed. Keep type/lint output separate.
- Fill the [test-layer matrix](../assets/test-layer-matrix.md) with exact commands,
  first-failure evidence, fixture teardown, and unexecuted environments.

## Primary official sources

- Testing Library guiding principles: <https://testing-library.com/docs/guiding-principles/>
- Testing Library query priorities: <https://testing-library.com/docs/queries/about/>
- Testing Library async assertions: <https://testing-library.com/docs/dom-testing-library/api-async/>
- Playwright browser-test isolation: <https://playwright.dev/docs/browser-contexts>
