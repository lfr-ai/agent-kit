# Browser journey acceptance contract

- Journey and observable outcome: {{task, success text/record/URL}}
- Installed runner and browser project: {{tool, version, existing command}}
- Approved runtime/base URL: {{local synthetic environment; never credentials}}
- Setup and reset: {{fixture identity, independent setup, finally/teardown}}
- Real boundaries: {{routing, components, backend integration}}
- Simulated boundaries and limits: {{transport failures/external services}}

## Acceptance scenarios

| Given | When | Then | Locator/readiness contract |
| --- | --- | --- | --- |
| Isolated fixture at direct task URL | Complete the critical task | User sees completion and promised persisted/URL state | {{role/name, exact outcome}} |
| Same fixture with first request rejected | Activate retry by keyboard | Error clears, task completes once, focus is usable | {{error, retry, focus target}} |
| No records | Load task view | Empty explanation and next action are available | {{empty state and action}} |
| Long labels at narrow width | Navigate by keyboard | Task remains reachable without obscured focus | {{viewport, target}} |
| Pending work | Navigate away, then complete old request | New route remains unchanged by abandoned work | {{route and non-leak assertion}} |
| URL-addressable state, if present | Refresh, back and forward | URL and rendered selection agree | {{URL/state assertion}} |

## Execution record

- Focused command/result: {{exact command, test count, exit status or blocked}}
- Timing-risk repeat command/result: {{repeat count and first failure evidence}}
- Failure capture: {{sanitized trace/log path and retention}}
- Cleanup evidence: {{fixture removed, no cross-test state}}
- Remaining browser/environment gaps: {{not run and why}}
- Decision and regression owner: {{accept / repair / blocked; owner}}
