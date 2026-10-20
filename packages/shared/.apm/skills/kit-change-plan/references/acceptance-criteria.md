# Acceptance criteria

Acceptance criteria turn a request into checks that decide when the change is
done. Write them before planning slices; every slice later proves one or more
of them.

## Properties of a good criterion

- **Observable**: describes behavior at a boundary someone can exercise (an
  API response, a command's output, a stored record, a page), not an
  implementation detail.
- **Binary**: a reviewer can say pass or fail without debate.
- **Testable now**: the environment needed to check it exists or is listed as a
  prerequisite.
- **Independent of solution**: it does not prescribe classes, tables or
  libraries unless that is a real constraint.
- **Covers failure**: invalid input, missing permission and unavailable
  dependency each have an expected result.

## Formats

### Given / When / Then

Good for behavior with clear preconditions:

```gherkin
Scenario: reject an invoice with a negative line amount
  Given an open order with one line item
  When the client submits an invoice line with amount -5.00
  Then the response status is 422
  And the error names the field "lines[0].amount"
  And no invoice is stored
```

### Rule list

Good for constraints and non-functional requirements:

- Export of 100 000 invoices completes within 60 seconds on the reference
  environment.
- Exported files contain no personal data fields beyond the customer number.
- The command exits with status 2 and a usage message when `--since` is not an
  ISO date.

## Coverage checklist

For each criterion set, ask whether you have one for:

| Area | Example question |
| --- | --- |
| Happy path | does the main scenario produce the stated result? |
| Boundaries | empty, one, maximum, one over maximum, time zones, rounding |
| Invalid input | what error, which status, what is not changed? |
| Authorization | who may and may not do this? |
| Concurrency and retries | what happens on duplicate submission or retry? |
| Persistence and migration | do existing records still work? |
| Observability | what is logged or measured, without sensitive data? |
| Compatibility | which existing callers, formats or defaults must not change? |
| Performance | is there a limit that matters to users? |
| Accessibility | for UI: keyboard, screen reader, contrast expectations |

Not every area applies; write "not applicable" consciously instead of skipping.

## From criteria to tests

Each criterion maps to at least one automated test at the lowest level that
still observes the behavior (a unit test for a pure rule, an integration test
for persistence, an end-to-end test only for the critical journey). Record the
mapping in the plan's slice table so a reviewer can see which test proves what.

## Pitfalls

- "The code is clean" or "works correctly": not binary. Replace with checks.
- Criteria written after implementation describe what was built, not what was
  needed.
- Criteria that only cover the happy path lead to error handling invented
  during review.
- A long list of tiny criteria for a trivial change is overhead; a one-line fix
  needs one criterion and one regression test.

## Sources

- [Cucumber: Gherkin reference](https://cucumber.io/docs/gherkin/reference/)
- [Agile Alliance: acceptance testing](https://agilealliance.org/glossary/acceptance-testing/)
- [GitHub: about issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/about-issues)
