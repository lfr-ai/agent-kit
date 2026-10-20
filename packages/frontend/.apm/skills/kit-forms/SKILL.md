---
name: kit-forms
description: Use when building or changing user input forms with validation, submission, and recovery behavior.
license: MIT
---

# Make form behavior explicit

## Resources

- [Submission guide](references/guide.md): ambiguous outcomes and draft recovery.
- [Form patterns](references/form-patterns.md): approach choice, schema rules,
  validation timing, submission lifecycle, arrays, server errors, anti-patterns.
- [Field anatomy and messages](references/field-anatomy.md): markup order,
  input types, autocomplete, groups, error summary, wording.
- [Form acceptance contract](assets/form-acceptance.md) to fill per form.
- Templates: [schema and request mapping](assets/invoice-form.schema.ts.template),
  [field component](assets/form-field.tsx.template),
  [server error mapping](assets/apply-server-errors.ts.template),
  [form](assets/invoice-form.tsx.template) with
  [behavior tests](assets/invoice-form.test.tsx.template).

## Procedure

1. Read the guide; fill the acceptance contract before changing behavior.
2. List fields, requiredness, formats, dependencies, and the receiving API
   contract, including its error format and idempotency support.
3. Choose the approach with the form patterns decision table; reuse the form
   library the project already has.
4. Write one schema; derive types from it; map values to the request in one
   tested function.
5. Use native form semantics, matching input types, and `autocomplete` tokens.
6. Keep labels, hints, optional markers, and errors associated with controls.
7. Validate client-side for prompt feedback; keep server validation authoritative.
8. Never clear user input when a request fails.
9. Prevent accidental double submits; keep one idempotency key per logical
   submission so retries after ambiguous failures are safe when the server
   honors it.
10. Map server field errors to controls; keep unknown errors as a readable summary.
11. Focus the first invalid control or the summary after a failed submission.
12. Test valid, malformed, cross-field, server rejection, network failure, retry,
    and dynamic rows; report which validation and browser checks actually ran.

## Acceptance gates

- [ ] Schema-derived types and a tested request mapping exist.
- [ ] Every control has a visible label and linked hint/error text.
- [ ] Failed submits focus the right element and preserve all input.
- [ ] Double submit produces one request; retries reuse the idempotency key.
- [ ] Server field errors appear inline; unknown errors appear in a summary.
- [ ] Keyboard-only completion and row management work.
