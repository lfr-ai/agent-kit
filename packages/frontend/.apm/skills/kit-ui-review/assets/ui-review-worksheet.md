# Rendered UI state and finding worksheet

- Task, route and intended outcome: {{scope}}
- Build/browser, viewport, locale, input method: {{environment}}
- Synthetic fixture/reset and capture safety: {{setup, redaction/retention}}
- Evidence mode: {{source / screenshot / interactive / scanner / screen reader}}

## State coverage

Use observed / blocked / not applicable with a reason; add evidence, not just ticks.

| State | How reached | Expected next action/feedback | Observation and evidence |
| --- | --- | --- | --- |
| Pending | {{delayed operation}} | Progress without premature success | {{result}} |
| Empty / filtered empty | {{fixtures for each}} | Onboard or clear filters appropriately | {{result}} |
| Success | {{confirmed operation}} | Clear outcome, correct target and state | {{result}} |
| Validation failure | {{invalid draft}} | Associated errors, reachable correction, draft kept | {{result}} |
| Permission/session failure | {{safe denied fixture}} | Honest denial and allowed navigation | {{result}} |
| Network failure then retry | {{failed transport}} | Work preserved, readable retry outcome | {{result}} |
| Destructive cancel/confirm | {{separate safe fixtures}} | No change on cancel; stated effect on confirm | {{result or absent}} |

## Interaction and layout coverage

- Keyboard order, activation, focus and announcements: {{observed sequence}}
- Narrow/wide, 320 CSS px reflow, 200% text: {{sizes and results}}
- Long labels/unbroken values/translated text: {{cases and clipping/wrapping}}
- Contrast, color-independent meaning, forced colors/reduced motion: {{results}}
- Existing terminology/token comparison: {{specific neighbor and difference}}

## Repeat per finding

- Severity and blocked/harmed task: {{blocker/major/minor with impact}}
- Reproduction: {{state, actions, actual versus expected}}
- Evidence location and type: {{sanitized capture or interactive observation}}
- Smallest repair and owner: {{boundary, recommendation}}
- Original plus adjacent-state retest: {{sequence, result or pending}}
- Acceptance/remaining limits: {{decision, unobserved cases, next prerequisite}}
