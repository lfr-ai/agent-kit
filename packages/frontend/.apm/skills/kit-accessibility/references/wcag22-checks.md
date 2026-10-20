# WCAG 2.2 AA checks for application interfaces

This maps WCAG 2.2 Level A and AA success criteria that commonly apply to web
application screens to the cheapest reliable verification method. It is a
working aid, not a conformance claim; the normative text is the standard.

Legend: **auto** = axe or another rule engine can detect common failures;
**test** = component or browser test can assert it; **manual** = needs human
judgment or assistive technology.

## Perceivable

| Criterion | What to check | Method |
| --- | --- | --- |
| 1.1.1 Non-text Content (A) | images have meaningful `alt` or `alt=""` if decorative; icon buttons have names | auto + manual (quality of text) |
| 1.3.1 Info and Relationships (A) | headings, lists, tables, labels, fieldsets expressed in markup | auto + test |
| 1.3.2 Meaningful Sequence (A) | DOM order matches visual reading order | manual |
| 1.3.5 Identify Input Purpose (AA) | `autocomplete` tokens on personal data fields | auto + test |
| 1.4.1 Use of Color (A) | state not conveyed by color alone | manual |
| 1.4.3 Contrast (Minimum) (AA) | text 4.5:1, large text 3:1 | auto (browser) |
| 1.4.4 Resize Text (AA) | 200% text zoom without loss | manual |
| 1.4.10 Reflow (AA) | 320 CSS px width, no two-dimensional scrolling for text | browser test at 320px viewport + manual |
| 1.4.11 Non-text Contrast (AA) | control boundaries, focus indicators, icons 3:1 | manual (tools assist) |
| 1.4.12 Text Spacing (AA) | increased line, letter, word spacing does not clip | browser test with injected CSS |
| 1.4.13 Content on Hover or Focus (AA) | tooltips dismissible, hoverable, persistent | manual + browser test |

## Operable

| Criterion | What to check | Method |
| --- | --- | --- |
| 2.1.1 Keyboard (A) | every function works with the keyboard | test + manual |
| 2.1.2 No Keyboard Trap (A) | focus can always leave (except modal dialogs, which close with Escape) | test |
| 2.1.4 Character Key Shortcuts (A) | single-key shortcuts can be turned off or remapped | manual |
| 2.2.1 Timing Adjustable (A) | session timeouts warn and allow extension | test + manual |
| 2.3.1 Three Flashes (A) | no flashing content | manual |
| 2.4.1 Bypass Blocks (A) | skip link or landmarks | auto + test |
| 2.4.2 Page Titled (A) | unique, descriptive `document.title` per route | test |
| 2.4.3 Focus Order (A) | order preserves meaning; focus moves sensibly on route change and overlays | test + manual |
| 2.4.4 Link Purpose (A) | link text meaningful in context | manual |
| 2.4.6 Headings and Labels (AA) | descriptive headings and labels | manual |
| 2.4.7 Focus Visible (AA) | visible focus indicator | browser test + manual |
| 2.4.11 Focus Not Obscured (Minimum) (AA, new in 2.2) | sticky headers, footers, banners do not fully hide focused element | browser test (scroll into view under sticky UI) + manual |
| 2.5.1 Pointer Gestures (A) | multipoint or path gestures have single-pointer alternatives | manual |
| 2.5.2 Pointer Cancellation (A) | activation on up-event; can abort | manual |
| 2.5.3 Label in Name (A) | accessible name contains the visible label | test |
| 2.5.7 Dragging Movements (AA, new in 2.2) | drag-and-drop has a click or keyboard alternative | test + manual |
| 2.5.8 Target Size (Minimum) (AA, new in 2.2) | targets 24 by 24 CSS px or spaced | auto (browser) + manual |

## Understandable

| Criterion | What to check | Method |
| --- | --- | --- |
| 3.1.1 Language of Page (A) | `<html lang>` set | auto |
| 3.1.2 Language of Parts (AA) | `lang` on passages in another language | manual |
| 3.2.1 On Focus (A) / 3.2.2 On Input (A) | no unexpected context change on focus or input | test |
| 3.2.3 Consistent Navigation (AA) / 3.2.4 Consistent Identification (AA) | same navigation order and names across pages | manual |
| 3.2.6 Consistent Help (A, new in 2.2) | help mechanisms in the same relative place | manual |
| 3.3.1 Error Identification (A) | errors described in text | test |
| 3.3.2 Labels or Instructions (A) | labels and format hints present | auto + test |
| 3.3.3 Error Suggestion (AA) | messages say how to fix | manual |
| 3.3.4 Error Prevention (AA) | legal, financial, data-deleting actions reversible, checked, or confirmed | test + manual |
| 3.3.7 Redundant Entry (A, new in 2.2) | previously entered data pre-filled or selectable | test |
| 3.3.8 Accessible Authentication (Minimum) (AA, new in 2.2) | no cognitive test; paste and password managers allowed | test + manual |

## Robust

| Criterion | What to check | Method |
| --- | --- | --- |
| 4.1.2 Name, Role, Value (A) | custom controls expose name, role, state | auto + test |
| 4.1.3 Status Messages (AA) | status conveyed via live regions without focus change | test + manual |

4.1.1 Parsing is obsolete and removed in WCAG 2.2.

## What automation cannot tell you

Automated engines find a minority of real barriers. They cannot judge whether
alternative text is meaningful, whether focus order makes sense, whether an
announcement is timely and not noisy, or whether the flow is usable with a
screen reader. Plan a manual keyboard walkthrough and a screen-reader pass for
each changed flow, using the [component checklist](../assets/component-checklist.md.template)
and the [accessibility worksheet](../assets/accessibility-worksheet.md).

## Sources

- WCAG 2.2: <https://www.w3.org/TR/WCAG22/>
- What's new in WCAG 2.2: <https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/>
- How to Meet WCAG (quick reference): <https://www.w3.org/WAI/WCAG22/quickref/>
- Understanding WCAG 2.2: <https://www.w3.org/WAI/WCAG22/Understanding/>
- axe-core rule descriptions: <https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md>
- WAI, easy checks: <https://www.w3.org/WAI/test-evaluate/preliminary/>
