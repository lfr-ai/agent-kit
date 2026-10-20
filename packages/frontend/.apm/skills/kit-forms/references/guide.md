# Form validation and recoverable submission

## Verification prerequisites

- Identify field schema, accepted formats, normalization rules, cross-field
  dependencies, server error shape, and duplicate/idempotency contract.
- Inspect the existing form library or native approach, installed test runner,
  localization conventions, and supported autofill/input methods. Reuse these
  rather than introduce a library for one form.
- Prepare synthetic valid, invalid, rejected, and timeout responses. Never use
  personal form data in screenshots, logs, or fixtures.

## Quality gates by submission boundary

| Boundary | Required contract |
| --- | --- |
| Input | Native form/control semantics, visible associated labels, requiredness and format hints; appropriate autocomplete and input type. |
| Validation | Client feedback aids correction; server remains authoritative. Normalize only under the field's documented data contract. |
| Draft | Preserve entered values through validation/server/network errors; no automatic sensitive-data persistence in browser storage. |
| Pending | Submit by pointer and Enter share one submission path; guard duplicate in-flight work without making status/recovery inaccessible. |
| Server rejection | Known field errors attach to controls; unknown/general errors have a readable summary, not a silent drop or raw exception. |
| Focus | After failed submit, focus the summary or first invalid field intentionally; hints/errors are programmatically related and not color-only. |
| Success | Clear/navigate only after confirmed success; state which draft was saved if the user can edit while submission is pending. |

Distinguish an identifier from a quantity: numeric-looking identifiers may need
leading zeros and are not automatically `type=number`. Avoid eager formatting
that disrupts composition input or cursor position. Disabling a control can
exclude its value from native form submission; capture/serialize intentionally.

## Negative cases

- Empty required field, whitespace-only input, malformed format, maximum boundary,
  long Unicode text, and a dependent-field change. Do not add arbitrary
  restrictions unsupported by the receiving contract.
- Double click and Enter during pending work: no duplicate in-flight command;
  pending feedback remains readable.
- Server rejects a known field, then an unknown field key: associate the known
  error and retain the unknown one in a safe summary without exposing internals.
- Reject the request, then retry with values intact: no stale errors or duplicate
  status announcements; retry is reachable by keyboard.
- Timeout after the server might have committed: do not label this definitely
  unsaved or blindly retry a non-idempotent command.
- Edit during pending work or navigate away: a late response must not overwrite
  a newer draft. Abort of client waiting does not imply rollback on the server.

## Recovery and verification

1. Keep draft and submission state separate. Define whether pending edits are
   allowed, which revision is being submitted, and how cancellation behaves.
2. For an ambiguous outcome, use the server's operation lookup or idempotency
   mechanism if available. Otherwise explain uncertainty and a safe next step;
   do not manufacture an idempotency key protocol client-side alone.
3. After rejection, retain values and expose correction/retry. Reset errors for
   the current attempt without hiding uncorrected field errors.
4. Test schema/normalization cheaply, then component input/submission and error
   focus with the installed harness. Use a real browser for native validation,
   autofill, composition, or navigation behavior that emulation cannot prove.
5. Fill the [acceptance contract](../assets/form-acceptance.md), recording exact
   checks, unmet server guarantees, and unavailable input environments.

## Primary official sources

- HTML form controls and submission: <https://html.spec.whatwg.org/multipage/forms.html>
- HTML constraint validation: <https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#constraint-validation>
- WAI accessible form validation: <https://www.w3.org/WAI/tutorials/forms/validation/>
- HTTP method and idempotency semantics: <https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2>
