# Handling diagnostic evidence safely

Browser evidence routinely contains credentials and personal data: cookies,
bearer tokens, one-time codes in URLs, form values, response bodies, screenshots
of real records. Treat every artifact as sensitive until checked.

## Rules

1. Reproduce with synthetic accounts and data. Never debug in a real user's
   session or with copied production data.
2. Prefer textual evidence (status codes, error names, stack frames, timings)
   over raw dumps.
3. Redact before sharing: URLs, headers, and bodies with the
   [redaction helpers](../assets/redact.ts.template) (tests:
   [redact.test.ts](../assets/redact.test.ts.template)).
4. Export HAR files "sanitized" or without content when the browser offers it,
   then run the [HAR checker](../assets/check_har.py) before attaching:

   ```powershell
   python check_har.py capture.har
   python check_har.py capture.har --allow-bodies   # bodies reviewed and neutral
   ```

   It reports `file:entry: message` for credential headers, cookies, sensitive
   query parameters, sensitive body fields, emails, and retained response bodies,
   and exits 1 on any finding. It never prints the values.
5. Screenshots and videos: synthetic data only; crop to the defect; blur
   anything personal that remains.
6. Traces (Playwright, performance) contain network payloads and DOM snapshots;
   apply the same review.
7. Attach evidence to the tracker with the shortest retention that serves the fix;
   delete local copies afterwards.

## What a good report contains

| Field | Example |
| --- | --- |
| Environment | browser and version, OS, viewport, zoom, build version, feature flags |
| Steps | numbered, minimal, starting from a known URL with synthetic data |
| Expected and actual | observable behavior, not interpretation |
| Evidence | first error with stack, failing request (redacted), timing |
| Scope | browsers and data tried; where it does not reproduce |
| Hypothesis | labeled as hypothesis, with the evidence that supports it |
| Fix and verification | changed contract, regression test layer, retest result |

A local console or a single reproduction does not establish a production
incident's cause or impact; say what the evidence covers.

## Acceptance gates

- [ ] Reproduction uses synthetic data and an explicit environment record.
- [ ] Observations and hypotheses are separated in the evidence record.
- [ ] Every shared artifact passed redaction review; HAR files passed the checker.
- [ ] The fix has a regression test at the layer where the fault is observable.
- [ ] The original sequence and nearby negative cases were retested.

## Sources

- Chrome DevTools, export HAR with sanitization: <https://developer.chrome.com/docs/devtools/network/reference#save-as-har>
- W3C Web Performance, HAR format (draft): <https://w3c.github.io/web-performance/specs/HAR/Overview.html>
- OWASP, logging cheat sheet (sensitive data): <https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html>
- Playwright, trace viewer: <https://playwright.dev/docs/trace-viewer>
