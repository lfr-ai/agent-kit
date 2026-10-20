# Accessible interaction: evidence and release gates

## Verification prerequisites

- Identify the changed task, supported browsers, assistive technologies, and
  required conformance level. The checks below are a focused WCAG 2.2 AA baseline,
  not a complete conformance audit.
- Obtain a rendered route and synthetic data for normal, pending, empty, and
  rejected states. Source-only inspection cannot prove focus or announcements.
- Use the existing test runner and any already configured accessibility scanner.
  Record browser/OS/screen-reader versions for manual evidence; do not install
  tooling or claim unperformed checks.

## Task-specific quality gates

| Surface | Required observation |
| --- | --- |
| Action and navigation | A button performs an action; a link has a real destination. Keyboard and pointer can complete the same task. |
| Input | Visible label supplies the accessible name; hints and errors are programmatically associated; requiredness is conveyed beyond color. |
| Focus | Tab order follows the task, focus is visible and not entirely obscured by author content; removal of the active control leaves a sensible focus destination. |
| Dialog, if present | Initial focus is intentional; modal interaction stays inside; an accessible close action exists; closing returns focus to the trigger or its logical successor. |
| Async feedback | Progress, success, and errors are discoverable without surprise focus changes; live regions do not announce every polling update. |
| Visual access | Normal text contrast is at least 4.5:1, large text 3:1, relevant UI boundaries and states 3:1 against adjacent colors, subject to WCAG exceptions. |
| Layout | Text remains usable at 200% resizing and content reflows at 320 CSS px without two-axis scrolling except essential two-dimensional content. |
| Targets and motion | Pointer targets meet the 24 by 24 CSS px size or spacing/other WCAG exception; reduced-motion preference removes nonessential motion. |

For each changed custom widget, select the matching ARIA APG pattern before
implementing keyboard bindings. Do not apply menu arrow-key behavior to ordinary
site navigation or add roles without the accompanying interaction.

## Failure modes and negative cases

- Close a dialog by keyboard after a server error; verify focus does not disappear
  into a removed element or remain trapped behind the overlay.
- Submit invalid input twice, then correct it. Errors must be readable, associated,
  and cleared when resolved, without duplicate stale announcements.
- Delay an operation, trigger an empty result, and disconnect the network.
  Loading indicators must have meaningful text and recovery must remain reachable.
- Use long translated labels, forced colors, zoom, and reduced motion. Look for
  clipped controls, invisible outlines, color-only warnings, and motion-only cues.
- Inspect the computed accessible name, not just the DOM text; `aria-label` can
  accidentally replace a visible label and break voice-control matching.

## Recovery and verification

1. Prefer restoring a native control or an existing tested primitive over adding
   more ARIA to repair contradictory semantics.
2. Fix focus at the lifecycle boundary that opens, closes, or removes content.
   Do not use arbitrary timers to hide a race.
3. Add a behavioral regression for the failed keyboard/error sequence using the
   installed runner. Run any configured scanner separately.
4. Repeat the original flow manually with keyboard and, where available, a
   screen reader. An accessibility tree is diagnostic evidence, not a substitute.
5. Complete the [worksheet](../assets/accessibility-worksheet.md), recording
   blockers, WCAG exceptions, and unavailable checks instead of a blanket pass.

## Primary official sources

- WCAG 2.2 criteria and exceptions: <https://www.w3.org/TR/WCAG22/>
- WAI forms guidance: <https://www.w3.org/WAI/tutorials/forms/>
- ARIA APG widget patterns: <https://www.w3.org/WAI/ARIA/apg/patterns/>
- WAI evaluation scope and methods: <https://www.w3.org/WAI/test-evaluate/>
