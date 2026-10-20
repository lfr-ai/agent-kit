---
description: Build or change a form with one schema, accessible fields, client and server validation, safe submission, and input preserved on failure.
argument-hint: The form and its fields, e.g. "invoice address form"
agent: agent
---

# Add or change a form

Deliver a form whose validation, submission, and recovery behavior are
explicit, accessible, and tested.

## Input

- The user-supplied argument names the form and, ideally, its fields. Ask for
  the receiving endpoint and its error format if the codebase does not show
  them.

## Procedure

1. Load [kit-forms](../skills/kit-forms/SKILL.md) and fill its form acceptance
   contract before changing behavior.
2. List each field with requiredness, format, dependencies on other fields,
   and the matching request property. Note the endpoint's error format and
   idempotency support.
3. Reuse the form library and field components the project already has.
   Choose the approach from the skill's form patterns.
4. Write one schema, derive types from it, and map values to the request in
   one tested function.
5. Use native semantics: matching input types, `autocomplete` tokens, visible
   labels, hints, and optional markers associated with each control.
6. Validate on the client for fast feedback; treat the server as authoritative.
7. Disable duplicate submission while pending and keep one idempotency key per
   logical submission.
8. On failure, keep every value the user entered. Map server field errors to
   their controls and show unknown errors in a readable summary.
9. After a failed submit, move focus to the first invalid control or to the
   error summary; announce success without stealing focus.
10. Write behavior tests: valid submit, each validation rule, server field
    error, network failure with retry, double submit, and keyboard-only use.
11. Review the result with [kit-accessibility](../skills/kit-accessibility/SKILL.md)
    and run type, lint, and test commands.

## Acceptance gates

- [ ] One schema is the source for types and validation.
- [ ] No input is lost on any failure path.
- [ ] Every error is tied to its field in text, not color alone.
- [ ] Tests cover validation, server errors, retry, and double submit.

## Output

The filled field table, files changed, test names mapped to the acceptance
contract, commands run with results, and any server behavior assumed but not
verified.
