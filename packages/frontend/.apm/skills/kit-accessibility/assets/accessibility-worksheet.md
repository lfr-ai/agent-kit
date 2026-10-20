# Accessibility interaction worksheet

Copy into the consumer's review record; replace braces with observations.
Use pass / fail / blocked / not applicable with a reason. Empty rows are not passes.

- Task and route: {{task, route, change}}
- Required standard and scope: {{level, widgets, excluded surfaces}}
- Environment: {{browser, OS, input methods, screen reader and versions}}
- Fixture and reset: {{synthetic data, state setup, cleanup}}

## Interaction evidence

| Sequence | Expected result | Status and observed evidence |
| --- | --- | --- |
| Complete task with Tab, Shift+Tab, Enter/Space | All actions work; visible focus follows logical order | {{result}} |
| Open and close overlay, including failure state | Focus enters appropriately and returns; no trap outside a modal | {{result or reason absent}} |
| Submit invalid data, navigate errors, correct and retry | Text errors are associated and reachable; resolved errors disappear | {{result}} |
| Wait through pending, empty, and failed operation | Status is discoverable; announcements are useful, not repetitive | {{result}} |
| Resize text 200%; check 320 CSS px reflow | No lost information or actions; record essential-content exceptions | {{result}} |
| Check text/UI contrast, focus, target size | Meets applicable thresholds; no color-only meaning | {{measurement and exception if any}} |
| Enable forced colors and reduced motion | Controls remain distinguishable; nonessential motion is reduced | {{result}} |
| Repeat representative flow with screen reader | Name, role, state, feedback and reading order support the task | {{result or unavailable}} |

## Finding and closure

- Blocked user action and reproduction: {{state, keys, actual vs expected}}
- Criterion/pattern and impact: {{reference, affected users}}
- Repair boundary: {{semantics, focus owner, labels, announcement, styles}}
- Regression and rerun evidence: {{test selector/command, manual sequence}}
- Remaining limitations and owner: {{unavailable environment or unresolved issue}}
- Decision: {{accept / repair / defer with owner and rationale}}
