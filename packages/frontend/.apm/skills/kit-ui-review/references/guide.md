# Rendered interface review with actionable findings

## Verification prerequisites

- Identify the changed task, route, intended user outcome and neighboring pattern.
  Record the browser/build, viewport, locale and input method.
- Obtain a safe rendered environment and synthetic fixtures for each state.
  Do not claim an unobserved state passed because its source branch exists.
- Distinguish source review, screenshot observation, interactive browser review,
  scanner output and screen-reader evidence. They answer different questions.
- Do not start an app or external service without the consumer's approved workflow.

## Task-specific quality gates

| Area | Acceptance gate |
| --- | --- |
| State completeness | Pending, empty, success, validation, denied and transport failure tell the truth and expose a safe next action. |
| Action clarity | Labels explain action and consequence; disabled actions explain why when otherwise unclear; progress is not mistaken for completion. |
| Recovery | Retry preserves relevant work; destructive actions have risk-appropriate confirmation or undo, with no false promise of reversibility. |
| Responsive layout | At narrow/wide sizes and 320 CSS px reflow, essential actions remain reachable; two-dimensional exceptions are justified. |
| Content | Long labels, unbroken values, translated text and larger text do not hide meaning or actions; truncation has an accessible full-value route. |
| Accessibility | Semantic names/roles, keyboard order, visible unobscured focus, error association and status feedback support the task. |
| Visual meaning | Color/icons are supplemented by text or semantics; contrast, reduced motion and forced-colors behavior remain usable. |
| Consistency | Terminology, spacing/tokens and interaction match established patterns unless a concrete task need justifies change. |

Review the decision a user must make, not only whether a screen looks balanced.
For high-risk destructive work, verify the target and consequences are clear,
cancel is safe, and repeated activation cannot silently repeat the operation.

## Negative cases to render

1. Start with no data and with filtered-to-zero results. Distinguish onboarding
   from "clear filters" recovery instead of using one misleading empty message.
2. Delay the primary action, reject it, then retry. Keep focus usable and edits
   intact; progress cannot cover the only available recovery action.
3. Deny access or expire the session. Do not show forbidden content behind a
   purely visual overlay; record server enforcement as a separate boundary.
4. Use long translated labels, a long unbroken identifier, large text, and a narrow
   viewport. Check wrapping, sticky headers, scroll regions and obscured focus.
5. Complete by keyboard with reduced motion/forced colors where supported.
   Hover-only hints and icon-only feedback must not be essential to completion.
6. Cancel a destructive action, then confirm it in a separate fixture. Verify
   no mutation on cancel and the advertised outcome/undo on confirmation.

## Finding severity and recovery

- **Blocker:** a required task cannot be completed, private/critical information
  is mishandled, or an essential control is inaccessible. Resolve before acceptance.
- **Major:** a supported state/input method loses work, hides recovery or creates
  a materially misleading outcome. Repair or record an explicit owner/decision.
- **Minor:** localized clarity/consistency defect with a usable workaround.
  Keep the concrete reproduction; do not label personal preference as a defect.

For each finding, record state, actions, actual/expected result, user impact and
evidence. Recommend the smallest repair to the established pattern. Rerun the
original sequence and an adjacent state after repair; a new screenshot alone
does not prove a focus or retry fix.

Use the [review worksheet](../assets/ui-review-worksheet.md). Mark each state
observed, blocked, or not applicable with a reason. Do not call source inspection
a browser review, or infer user-research conclusions from a single observation.

## Primary official sources

- WCAG 2.2 requirements: <https://www.w3.org/TR/WCAG22/>
- WAI preliminary evaluation: <https://www.w3.org/WAI/test-evaluate/preliminary/>
- WAI accessible notifications: <https://www.w3.org/WAI/tutorials/forms/notifications/>
- WAI ARIA widget behavior: <https://www.w3.org/WAI/ARIA/apg/patterns/>
