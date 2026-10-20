# Behavior-to-test-layer matrix

- Changed behavior and owner: {{feature/adapter/route}}
- Installed harness and environment: {{runner, DOM emulator or browser}}
- Existing focused command pattern: {{package script and selector syntax}}

## Allocation

| Observable contract | Risk/input | Chosen layer | Real boundary | Simulated seam | Assertion |
| --- | --- | --- | --- | --- | --- |
| {{parse/reduce}} | {{boundary/malformed}} | {{unit}} | {{transformation}} | {{none or input}} | {{exact result/rejection}} |
| {{interaction}} | {{pending/error/keyboard}} | {{component}} | {{render/input/state}} | {{transport}} | {{role/text/focus}} |
| {{integration}} | {{race/invalidation}} | {{integration}} | {{adapter/cache/router}} | {{response timing}} | {{new intent wins}} |
| {{critical journey}} | {{direct load/retry}} | {{browser or justified omission}} | {{cross-layer contract}} | {{external boundary}} | {{user outcome}} |

## Determinism checklist

- [ ] Fixtures are synthetic and independently created/reset.
- [ ] Clock, timezone, random IDs and locale are controlled only where relevant.
- [ ] Async assertions are awaited; retry callbacks contain no user actions.
- [ ] Responses can be deliberately delayed and resolved out of order.
- [ ] Mocks, handlers, timers, storage and listeners are restored per test.
- [ ] No production branch exists solely to make the test pass.
- [ ] DOM-emulated results are not reported as real browser/a11y verification.

## Execution and recovery

- New regression first fails because: {{assertion and fault, or not demonstrated}}
- Focused command and result: {{exact command, count, status}}
- Isolation/neighbor or repeat check: {{command and result}}
- First failure evidence and repaired cause: {{ordering, fixture, wait or product bug}}
- Type/lint results separately: {{commands or not run}}
- Untested boundaries and next prerequisite: {{server/browser/environment}}
