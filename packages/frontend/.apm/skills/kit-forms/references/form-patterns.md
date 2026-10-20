# Form patterns with React Hook Form and Zod

## Choosing the form approach

| Form shape | Approach |
| --- | --- |
| One or two fields, server decides validity (search, rename) | native `<form>` with React 19 `useActionState`, or the router's form action |
| Several fields, client feedback, no arrays | React Hook Form with a Zod resolver |
| Dynamic rows, conditional sections, dirty tracking, wizard steps | React Hook Form with `useFieldArray` and per-step schemas |
| Data grid editing | the grid's own editing model; validate on commit per row |

Use the library the project already has. Templates assume React Hook Form 7,
`@hookform/resolvers` 5, and Zod 4; for Zod 3 replace `{ error: ... }` with
`{ message: ... }` and `z.email()` / `z.iso.date()` with `z.string().email()` /
`z.string().date()`.

## Building blocks

| Piece | Template |
| --- | --- |
| Schema, defaults, request mapping, field-name guard | [invoice-form.schema.ts](../assets/invoice-form.schema.ts.template) |
| Field anatomy (label, hint, error, ARIA wiring) | [form-field.tsx](../assets/form-field.tsx.template) |
| Server error mapping and ambiguity detection | [apply-server-errors.ts](../assets/apply-server-errors.ts.template) |
| Complete form with line items and recovery | [invoice-form.tsx](../assets/invoice-form.tsx.template) |
| Behavior tests | [invoice-form.test.tsx](../assets/invoice-form.test.tsx.template) |

See [field anatomy and messages](field-anatomy.md) for markup and wording rules.

## Schema rules

- One schema per form; derive the TypeScript type with `z.infer`. Do not declare
  the type separately.
- Keep form values close to what inputs produce (strings for dates, numbers via
  `valueAsNumber`). Convert to the API shape in one mapping function
  (`toCreateInvoiceRequest`), which is unit-testable.
- Cross-field rules (`refine` with `path`) attach the message to the field the
  user must change.
- Messages say what to do, not what went wrong: "Enter a quantity", not
  "Invalid number".
- Client validation mirrors server rules for feedback only. The server re-validates
  everything; never rely on the client for authorization or business invariants.

## Validation timing

| Mode | Behavior | Use when |
| --- | --- | --- |
| `onSubmit` (default) | validate on submit, then re-validate on change | short forms |
| `onTouched` | validate a field on first blur, then on change | most forms; avoids errors while typing the first time |
| `onChange` | validate on every keystroke | rarely; noisy for screen-reader users |
| `onBlur` | validate on each blur | when change validation is expensive |

Do not show an error before the user has interacted with the field or submitted.

## Submission lifecycle

1. `handleSubmit` validates; on failure React Hook Form focuses the first invalid
   field (`shouldFocusError`).
2. On success the handler maps values to the request and calls the mutation.
3. While pending, the submit button is marked `aria-disabled`, ignores activation,
   stays focusable, and its label changes; other
   inputs stay editable unless editing would corrupt the in-flight request.
4. On a definitive rejection (4xx), map field errors inline with `setError`, show
   unmapped errors in a focused summary, keep every value.
5. On an ambiguous failure (network error, timeout, 5xx) say that the outcome is
   unknown and keep the same idempotency key for the retry, so a server that
   honors the key does not create a duplicate.
6. On success announce the result (`role="status"`) and either navigate or reset
   with fresh defaults, never both silently.

Blocking repeat activation prevents a double click in one tab; it does not make the server
operation idempotent. Duplicate prevention across tabs, reloads, and retries needs
a server contract (idempotency key, natural unique constraint, or version check).

## Field arrays

- Render rows from `fields` and key them by `field.id`, never the index.
- Labels include the row number ("Line 2 quantity") so each control has a unique
  accessible name.
- After appending, move focus to the new row's first control
  (`append(value, { shouldFocus: true })`). After removing, move focus to a
  sensible neighbor or the add button.
- Array-level errors from the resolver appear at `errors.lines.root` (or
  `errors.lines.message`); render them next to the group legend.

## Server errors

- Agree on one error format with the API, for example RFC 9457 problem details
  with an `errors` object keyed by field path (`lines.0.quantity`).
- Guard field names with a type predicate before calling `setError`; unknown
  names go to the summary instead of disappearing.
- 409 conflicts: tell the user the record changed and offer to reload; do not
  overwrite the other edit automatically.

## Unsaved changes

- `formState.isDirty` tells whether to warn. Use the router's navigation blocker
  for in-app navigation and `beforeunload` only while dirty.
- Remove the warning after a successful save, before navigating.

## Anti-patterns

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| Controlled `useState` per field plus manual validation | re-render per keystroke, duplicated rules | form library with schema |
| `reset()` in the catch block | user loses input after a failure | keep values; map errors |
| Placeholder as the only label | label disappears while typing | visible `<label>` |
| Error shown only by red border | invisible to screen readers and color-blind users | text message linked with `aria-describedby` |
| Disabling submit until the form is valid | users cannot discover what is wrong | enable submit; show errors on submit |
| Index keys for rows | values jump between rows on remove | `field.id` |
| Generating a new idempotency key per click | retries after a timeout duplicate the order | one key per logical submission |
| Catch-all "Something went wrong" | no recovery path | specific summary plus kept input |

## Acceptance gates

- [ ] Schema-derived types; one mapping function to the API shape with a unit test.
- [ ] Every control has a visible label, linked hint and error, and correct input
      type and `autocomplete` token.
- [ ] Tests cover empty submit focus, cross-field rule, double submit, server field
      errors, ambiguous failure with retry, and row add/remove.
- [ ] Input is preserved after every failure path.
- [ ] Keyboard-only completion works, including row management.

## Sources

- React Hook Form, `useForm`: <https://react-hook-form.com/docs/useform>
- React Hook Form, `useFieldArray`: <https://react-hook-form.com/docs/usefieldarray>
- React Hook Form, `setError`: <https://react-hook-form.com/docs/useform/seterror>
- Hook Form resolvers: <https://github.com/react-hook-form/resolvers>
- Zod 4 documentation: <https://zod.dev/>
- Zod 4 error customization: <https://zod.dev/error-customization>
- React, `useActionState`: <https://react.dev/reference/react/useActionState>
- RFC 9457 problem details: <https://www.rfc-editor.org/rfc/rfc9457.html>
- IETF draft, Idempotency-Key header: <https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/>
