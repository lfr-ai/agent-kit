# Flake triage

A flaky test passes and fails on the same code. Treat every flake as a defect in
the test, the application, or the environment, never as noise.

## Reproduce

1. Run the single test repeatedly: `npx playwright test orders.spec.ts -g "filters" --repeat-each=20 --workers=4`.
2. Add load: more workers, `--project` for the slowest browser, CPU throttling
   through the Chrome DevTools Protocol for Chromium only if needed.
3. Run in the CI container image locally when the flake only appears in CI.
4. Record the failure rate before and after the fix.

## Classify with the trace

Open the trace of a failed attempt (`npx playwright show-trace trace.zip`) and
compare the action timeline, DOM snapshots, network log, and console.

| Symptom in trace | Likely cause | Fix |
| --- | --- | --- |
| Click happened, nothing changed | element replaced during re-render, or handler attached after hydration | assert a ready state before acting; fix late handler attachment |
| Assertion saw old content | response order race; stale data rendered | assert the specific new content; fix race in app (abort or ignore stale responses) |
| Strict mode violation (multiple elements) | ambiguous locator, often during transitions | scope or name the locator precisely |
| Timeout waiting for request | request never sent, wrong route pattern, or cached | assert on UI; check route pattern and cache headers |
| Different data each run | shared test data or time-dependent fixtures | per-test data, fixed clock (`page.clock`) |
| Fails only in parallel | shared account or server state | per-worker accounts, unique data |
| Fails only in one browser | real compatibility defect or browser-specific timing | treat as product bug first |
| Animation mid-flight in screenshot | animations or transitions | `animations: "disabled"`, reduced motion |

## Time control

- `page.clock.install({ time })` fixes `Date` and timers in the page; use
  `page.clock.runFor` or `fastForward` to advance relative timers (debounce,
  polling, session expiry).
- Pin `timezoneId` and `locale` in the config so date formatting is stable.

## Fix order

1. Fix the application race if users can hit it (stale responses, double handlers,
   missing disabled states). Add a regression at the cheapest layer.
2. Fix the test's synchronization: assert the right ready signal.
3. Fix data isolation.
4. Only then consider quarantine: tag `@quarantine`, exclude from the blocking run,
   open a tracked issue with an owner and a date. Quarantine is temporary.

Never fix a flake by increasing timeouts globally or adding retries above the
suite's agreed limit.

## Report

For each flake record: test id, failure rate before and after, root cause class
from the table, fix location (app, test, data, environment), and the trace or
artifact reference. Do not attach artifacts containing personal data.

## Acceptance gates

- [ ] Flake reproduced with a measured failure rate, or documented as not
      reproducible with the attempts made.
- [ ] Root cause classified from trace evidence.
- [ ] Fix verified with `--repeat-each` at the original load.
- [ ] Any quarantine has an owner, issue, and expiry.

## Sources

- Playwright, trace viewer: <https://playwright.dev/docs/trace-viewer>
- Playwright, clock: <https://playwright.dev/docs/clock>
- Playwright, retries: <https://playwright.dev/docs/test-retries>
- Playwright, command line: <https://playwright.dev/docs/test-cli>
- Playwright, emulation (locale, timezone): <https://playwright.dev/docs/emulation>
