# Stable browser journey contracts

## Verification prerequisites

- Inspect the consumer's installed browser runner, browser versions, base URL,
  startup policy, fixture API, and cleanup mechanism. Do not install a new runner
  or start an external service implicitly.
- Select one critical outcome crossing real routing and rendering. Describe
  which backend boundary is real and which external dependency is simulated.
- Use dedicated synthetic accounts/data and isolated browser contexts. Any
  authentication-state file, trace, or screenshot needs the same care as secrets.
- If the approved app or browser binaries are unavailable, deliver test design
  and mark runtime verification blocked; DOM emulation is not browser evidence.

## Quality gates

| Contract | Gate |
| --- | --- |
| Setup | Each test can run alone and in any order; test data has a unique namespace and deterministic reset. |
| Locators | Prefer role plus accessible name; scope within the relevant region. Use a stable test ID only when semantics do not identify the target. |
| Waiting | Register a request/event wait before the triggering action; use retrying assertions on meaningful UI states rather than fixed sleeps. |
| Outcome | Assert the completed user task, not merely a click or HTTP response. Include URL/persistence if promised. |
| Failure | Error/empty states have readable feedback and a working retry or safe alternative; no success assertion can pass on an error page. |
| Input | Include a keyboard path and focus assertion for changed dialogs, validation, or navigation. |
| Isolation | Cleanup runs even on assertion failure; a leftover fixture cannot affect a later test. |

Keep routing and component state real when intercepting transport. Explicitly
separate fully stubbed journeys from end-to-end integration evidence. A generic
"network idle" wait can never settle with polling and can miss actual readiness.

## Negative cases worth the browser cost

- Load the target URL directly and refresh it; verify the host/router contract
  rather than relying on a test that always begins on the home page.
- Fail the task's network request once, retry it, then confirm exactly one
  resulting record or visible action where duplicate prevention is promised.
- Return empty data and long labels at a narrow viewport; the recovery action
  must remain reachable and not be obscured.
- Navigate back/forward after a filter or detail transition; verify URL and
  rendered state agree.
- Delay a response then leave the route; the next view must not display old data,
  unexpected focus changes, or leaked subscriptions.

## Failure diagnosis and recovery

1. Preserve the first failure trace and sanitized browser/server logs before
   rerunning. A retry pass does not explain the first failure.
2. Reproduce in isolation with the same fixture and browser; check locator
   ambiguity, unmet preconditions, response ordering, and incomplete cleanup.
3. Fix the cause. Do not extend all timeouts, add blanket retries, force clicks,
   or bypass disabled controls to hide broken interaction.
4. Run the focused journey, its negative case, and a repeat run for timing risks.
   Use the repository's repeat option if available; record count and failures.
5. Keep test data cleanup scoped to the fixture identity, never broad deletion
   in a shared environment. Report unverified browser projects explicitly.

Complete the [journey contract](../assets/journey-contract.md); it is an executable
test design worksheet, not a claim that a browser has run.

## Primary official sources

These examples describe principles, not a requirement to adopt Playwright.

- Playwright isolation and assertions: <https://playwright.dev/docs/best-practices>
- Playwright resilient locators: <https://playwright.dev/docs/locators>
- Playwright trace investigation: <https://playwright.dev/docs/trace-viewer>
- WAI keyboard operation: <https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html>
