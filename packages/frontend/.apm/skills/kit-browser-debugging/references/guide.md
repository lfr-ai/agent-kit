# Browser defect isolation

## Verification prerequisites

- Have permission to inspect the target environment and a synthetic fixture that
  reproduces the symptom. If no browser/runtime is available, limit the result to
  source hypotheses and explicitly mark reproduction blocked.
- Record browser/version, route with sensitive parameters removed, viewport,
  build identity, authentication state, and cache/service-worker conditions.
- Identify the installed runner and available source maps. Missing maps reduce
  stack precision; do not publish proprietary maps or upload diagnostics elsewhere.

## Isolation procedure and quality gates

1. Write the exact action sequence and expected observable result before changing
   anything. Require a repeatable failure or an explicitly intermittent frequency.
2. Capture the earliest relevant exception and its initiator/call stack. Later
   rendering failures may be consequences rather than causes.
3. Inspect the failed request: initiator, status, content type, safe response
   shape, redirect chain, timing, and cache source. An HTTP 200 containing an HTML
   login page is not a successful JSON contract.
4. Check DOM existence, computed visibility, stacking/overflow, event interception,
   active focus, and the accessibility tree. A visually present control may be
   hidden to assistive technology or covered by another element.
5. Change one variable per probe: warm versus cold cache, delayed response,
   viewport, browser, or route. Record predicted and actual observations. Do not
   clear every storage mechanism at once and call the disappearance a root cause.
6. Select the owning boundary only after evidence distinguishes response/schema,
   state race, asset/cache version, layout, or event/focus behavior.

## Failure modes and negative cases

| Probe | What it distinguishes |
| --- | --- |
| Reload the direct route, then navigate in-app | Hosting fallback or asset path defect versus client routing defect |
| Delay request A; complete newer B first | Stale response overwriting newer user intent |
| Navigate away before response or reconnect | Unowned callbacks, duplicate listeners, missing cleanup |
| Retry with empty body, invalid JSON or denied response | Success-path assumptions versus explicit adapter/error handling |
| Keyboard activation at narrow width | Pointer-only handler, hidden focus, overlay interception |
| Warm cache versus explicitly controlled cold cache | Stale chunks, service-worker versions, response caching |

Do not bypass CORS, disable authentication, or turn off browser security to make a
failure disappear. Such probes change the contract and are not repairs.

## Recovery and regression gates

- Save a sanitized reproduction before modifying local site data. Reset only the
  approved synthetic origin/fixture; never clear unrelated browsing data.
- Repair the smallest proven owner. For cache faults, verify both fresh and
  already-open clients; "clear your cache" is not durable recovery.
- Add a test where the contract fails: parser, component race, route, or browser
  interaction. Keep the original ordering/timing trigger in the regression.
- Repeat the exact reproduction and one neighboring sequence (refresh, retry,
  keyboard, navigation away). Check console and network for new failures.
- Report observed scope and unsupported environments separately from guesses.
  A screenshot, local console, or clean type check does not certify production.

Use the [evidence record](../assets/browser-evidence.md) for the causal chain.
HARs, traces, screenshots, console exports, and storage dumps can all contain
secrets; collect minimally and redact before attaching.

## Primary official sources

- Chrome DevTools network inspection: <https://developer.chrome.com/docs/devtools/network/>
- Chrome DevTools JavaScript debugging: <https://developer.chrome.com/docs/devtools/javascript/>
- Chrome DevTools accessibility: <https://developer.chrome.com/docs/devtools/accessibility/reference>
- Browser Fetch behavior: <https://fetch.spec.whatwg.org/>
