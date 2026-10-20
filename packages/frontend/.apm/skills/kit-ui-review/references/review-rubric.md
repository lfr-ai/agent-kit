# UI review rubric

Review the rendered interface, not the source alone. For each screen, walk the
user task through every state in the [review matrix](../assets/review-matrix.json.template)
and record findings in the [report](../assets/review-report.md.template).

## 1. Task and hierarchy

- The page states its purpose in the `h1` and title within one glance.
- The primary action is visually dominant and there is at most one per view.
- Secondary and destructive actions are distinguishable from the primary one.
- Information order follows the user's decision order, not the data model.

## 2. State completeness

| State | Questions |
| --- | --- |
| Loading | Does layout stay stable (skeleton sized like content)? Is progress announced politely? Is there a timeout path? |
| Empty | Does it explain why it is empty and offer the next action (create, clear filters)? |
| Populated | Do realistic volumes (1, 7, 100+ items) work? Is pagination or virtualization needed? |
| Long content | Do long names, numbers, and translations wrap or truncate with full text available? |
| Validation error | Are errors next to fields, in text, and summarized when the form is long? |
| Permission denied | Does the user understand what is missing and whom to ask? No dead buttons. |
| Network failure | Is data kept, the failure explained, and retry offered? Is stale data labeled? |
| Success | Is completion confirmed, and is the next step obvious? |
| Pending action | Is double activation prevented while focus stays on the control? |

## 3. Layout and responsiveness

- No horizontal scrolling at 320 CSS px for text content; tables offer a
  scrollable region or a stacked layout.
- Line length roughly 45 to 90 characters for paragraphs on wide screens.
- Touch targets at least 24 by 24 CSS px (44 by 44 preferred on touch layouts).
- Sticky headers or footers never cover the focused element.
- Content survives 200% zoom and text-spacing overrides
  ([layout resilience spec](../assets/layout-resilience.spec.ts.template)).

## 4. Content

- Labels and buttons use verbs that name the outcome ("Save invoice", not "OK").
- Terminology matches neighboring screens and the domain glossary.
- Numbers, dates, and currencies use the user's locale; units are explicit.
- Error messages say what happened and how to fix it, without blame.
- Text is not baked into images; no reliance on "click here".
- Pseudo-localized builds ([helper](../assets/pseudo-locale.ts.template),
  [tests](../assets/pseudo-locale.test.ts.template)) show no hard-coded strings,
  clipping, or concatenated sentences.

## 5. Interaction

- Every control shows hover, focus, active, disabled, and pending states.
- Destructive actions are confirmed or undoable; undo is preferred for frequent
  actions.
- Unsaved changes are protected when navigating away.
- Feedback appears near the action and within about 100 ms (or progress is shown).
- Motion is purposeful, short, and disabled under reduced-motion preference.

## 6. Accessibility essentials

- Keyboard path through the task works in a sensible order with visible focus.
- Headings form an outline; landmarks exist; images have suitable text
  alternatives.
- Color is never the only signal (status chips include text or icons).
- Contrast meets AA in light, dark, and forced-colors modes.
- Status and errors are announced (see the accessibility capability for depth).

## 7. Consistency

- Spacing, typography, and components come from the shared library and tokens.
- Similar actions are placed in the same position as on neighboring screens.
- Icons have consistent meaning across the product.

## Severity guidance

Rate by impact on the user task, not by implementation effort. When unsure
between two levels, choose the higher one and explain the uncertainty.
Accessibility barriers that block a task are blockers even if few users are
affected.

## Evidence discipline

- Record the exact state, viewport, preference, and locale for each finding.
- Screenshots use synthetic data and are cropped to the finding.
- Separate observation ("the error appears below the fold at 390px") from
  inference ("users may miss it").
- Mark states you could not reach; a source review or a single screenshot is
  not verification of interactive behavior.

## Sources

- WCAG 2.2: <https://www.w3.org/TR/WCAG22/>
- WAI, designing for web accessibility: <https://www.w3.org/WAI/tips/designing/>
- WAI, writing for web accessibility: <https://www.w3.org/WAI/tips/writing/>
- MDN, responsive design: <https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design>
- MDN, `prefers-reduced-motion`: <https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion>
- W3C Internationalization, text size in translation: <https://www.w3.org/International/articles/article-text-size>
- Playwright, emulation: <https://playwright.dev/docs/emulation>
