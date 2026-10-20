# Field anatomy and messages

## Markup order

```html
<div class="form-field">
  <label for="f1">Due date</label>
  <p id="f1-hint">On or after the issue date.</p>
  <p id="f1-error"><span class="visually-hidden">Error: </span>Enter the due date.</p>
  <input id="f1" type="date" aria-describedby="f1-hint f1-error" aria-invalid="true" />
</div>
```

- The label is visible and programmatically associated (`for`/`id` or wrapping).
- Hint and error come before the input so they are read before the user starts
  typing and stay visible above the on-screen keyboard.
- `aria-describedby` lists hint then error; remove the error id when it clears.
- `aria-invalid="true"` only while an error is shown.
- Mark optional fields "(optional)" instead of asterisks on required fields, or
  explain the asterisk once at the top. Required fields may also carry
  `aria-required="true"`; avoid the native `required` attribute when using
  `noValidate` custom messages, so browsers do not show conflicting bubbles.

## Input types and autocomplete

| Data | Markup |
| --- | --- |
| Email | `type="email" autocomplete="email"` |
| Phone | `type="tel" autocomplete="tel"` |
| Whole number | `type="number" inputmode="numeric" step="1"`, or `type="text" inputmode="numeric" pattern="[0-9]*"` for codes with leading zeros |
| Money | `type="number" inputmode="decimal" step="0.01"` or text with parsing for locales using a decimal comma |
| Date | `type="date"` when a picker helps; three text fields for memorable dates such as birth dates |
| Password | `type="password" autocomplete="current-password"` or `"new-password"`; allow paste |
| Name, address | the matching `autocomplete` tokens (`given-name`, `street-address`, `postal-code`) |

WCAG 2.2 success criterion 1.3.5 (Identify Input Purpose) expects `autocomplete`
tokens for personal data fields. Criterion 3.3.7 (Redundant Entry) means
previously entered information is pre-filled or selectable within one process.
Criterion 3.3.8 (Accessible Authentication) forbids cognitive tests such as
transcribing codes without paste or password-manager support.

## Groups

- Related radios and checkboxes go in `<fieldset>` with a `<legend>` that asks the
  question.
- Repeated row groups use a list or fieldset per row with row-numbered labels.
- A group-level error is rendered next to the legend and referenced from the
  fieldset (`aria-describedby` on the fieldset).

## Error summary

For long forms, show a summary at the top after a failed submit:

- container `role="alert"` or focused with `tabindex="-1"` (one of the two; both
  can double-announce in some screen readers);
- heading "There is a problem" or a specific title;
- a list of links, each pointing to the field id, with the same text as the
  inline error.

For short forms, focusing the first invalid field is enough. The
[invoice form](../assets/invoice-form.tsx.template) uses a summary only for
errors that have no field.

## Message wording

| Situation | Pattern | Example |
| --- | --- | --- |
| Missing required value | Enter / Select + what | "Enter the due date." |
| Wrong format | Enter + format with example | "Enter an email address like `name@example.com`." |
| Out of range | Must be + bound | "Quantity must be at least 1." |
| Cross-field | relation in plain words | "The due date must be on or after the issue date." |
| Server conflict | what happened + next step | "This record changed since you opened it. Review the latest version and try again." |
| Unknown outcome | uncertainty + reassurance + action | "We could not confirm that your changes were saved. Your input is kept; try again." |

Avoid blame ("You entered an invalid…"), codes without explanation, and messages
that disappear on a timer.

## Acceptance gates

- [ ] Each control's accessible name and description match the visible label,
      hint, and error (assert with `toHaveAccessibleDescription`).
- [ ] Personal data fields carry correct `autocomplete` tokens.
- [ ] Errors are text, not color alone, and persist until fixed.
- [ ] Group errors are associated with their fieldset.
- [ ] Paste is allowed in every field, including passwords and codes.

## Sources

- WAI tutorials, forms: <https://www.w3.org/WAI/tutorials/forms/>
- WCAG 2.2 Understanding 1.3.5 Identify Input Purpose: <https://www.w3.org/WAI/WCAG22/Understanding/identify-input-purpose>
- WCAG 2.2 Understanding 3.3.1 Error Identification: <https://www.w3.org/WAI/WCAG22/Understanding/error-identification>
- WCAG 2.2 Understanding 3.3.7 Redundant Entry: <https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry>
- WCAG 2.2 Understanding 3.3.8 Accessible Authentication (Minimum): <https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum>
- HTML Living Standard, autofill: <https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill>
- MDN, `inputmode`: <https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Global_attributes/inputmode>
- WAI-ARIA, `aria-describedby`: <https://www.w3.org/TR/wai-aria-1.2/#aria-describedby>
