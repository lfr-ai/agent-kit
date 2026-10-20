# Stage 3: Specify

Specify converts the accepted scope into requirements that a test can prove or
disprove. A requirement states an obligation; a scenario is a concrete example
that demonstrates it. Requirements without scenarios are wishes.

## Entry criteria

- `Status: proposed` with owner acceptance recorded.
- The living spec for each affected capability has been read, so modified
  requirements reuse existing wording where it is still correct.

## Activities

1. Copy [the requirements template](../assets/requirements.md.template) to
   `requirements.md`.
2. For each "What changes" bullet, write one or more requirements using the
   grammar in [the lifecycle overview](lifecycle.md#requirement-grammar):
   `## REQ-NNN <title>`, a `Change:` line, and a statement with an uppercase
   normative keyword.
3. Choose the keyword deliberately: MUST for an absolute obligation, SHOULD for
   a strong default with documented exceptions, MAY for optional behavior.
   Never use lowercase "must" to dodge the checker.
4. Write at least one scenario per requirement. Prefer three: the ordinary
   case, a boundary (empty, maximum, exactly-at-limit) and a failure (invalid
   input, missing permission, dependency timeout).
5. Write steps in domain language with concrete values: "Given two invoices
   dated 2026-03-02 and 2026-03-30", not "Given some data". Keep one `When` per
   scenario; two actions usually mean two scenarios.
6. Make each `Then` observable from outside the unit under test: a response, a
   stored record, an emitted event, a log line with a stable key. Avoid "the
   function is called".
7. For `Change: modify`, quote the old statement under a `Previously:` line so
   reviewers can see the delta. For `Change: remove`, add `Reason:` and point
   to the replacing requirement if any.
8. Run the checker; fix every finding, then set `Status: specified`.

## Writing scenarios that test well

| Weak step | Strong step |
| --- | --- |
| Given a user | Given a signed-in user with the role `billing-viewer` |
| When they export | When they request the export for March 2026 |
| Then it works | Then the response status is 200 and the body has 3 lines |
| Then an error is shown | Then the response is a problem document with type `invalid-month` |

Scenario outlines (one scenario repeated over a table of values) are fine in
tools that support them. In plain Markdown, write the table under the scenario
and keep one `When`/`Then` pair that refers to its columns.

## Exit criteria

- Every active requirement has a statement with a normative keyword and at
  least one scenario with `When` and `Then` steps.
- Every proposal bullet maps to at least one requirement, and no requirement
  falls outside the proposal's scope.
- No `TBD` remains in `requirements.md`.

## Acceptance gate

```text
python assets/check_spec_change.py <changes>/<id> --required proposal.md --required requirements.md
```

exits 0, and a reviewer confirms each scenario is something a test can assert.
Continue with [plan](stage-plan.md).

## Anti-patterns

- Restating implementation ("The service MUST call the repository").
- Scenarios that share hidden state or depend on execution order.
- One giant requirement with ten scenarios covering unrelated rules.
- Copying acceptance criteria from a ticket without making values concrete.

## Sources

- [Gherkin reference](https://cucumber.io/docs/gherkin/reference/)
- [RFC 2119: Key words for use in RFCs](https://www.rfc-editor.org/rfc/rfc2119)
- [RFC 8174: Ambiguity of uppercase vs lowercase in RFC 2119 key words](https://www.rfc-editor.org/rfc/rfc8174)
