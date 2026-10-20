# Verification matrix

Each layer proves something different. Collect evidence at every level and
report each by name; never let a lower level stand in for a higher one.

## Levels

| Level | Proves | Typical evidence | Does not prove |
| --- | --- | --- | --- |
| Contract lint | The specification is valid and follows conventions | Linter output on the contract file | That anyone implements it |
| Backend unit and domain tests | Rules and edge cases in isolation | Test run at the revision | Wiring, serialization, auth |
| Backend boundary tests | Routing, validation, serialization, error mapping, authorization | HTTP-level tests against the app | Behavior with real infrastructure |
| Provider contract tests | Real responses match the specification | Response validation in the backend suite | That the client parses them |
| Frontend component tests | Rendering and interaction per state | Tests using contract-validated fixtures | Real network behavior |
| Consumer contract checks | Fixtures and generated client match the specification | Regeneration drift check | Server behavior |
| Infrastructure preview | Exactly the intended resource changes | Plan or what-if output | Runtime connectivity |
| Integrated journey | The user outcome across real services | Browser or API journey against an environment | Scale, long-term reliability |
| Accessibility | Keyboard, focus, names, contrast, announcements for every state | Automated scan plus manual keyboard pass | Usability for every user |
| Mixed-version compatibility | Rollout steps are safe | Journey or contract run for old-new pairs | Unplanned version combinations |
| Post-release signals | Health in production | Error rate, latency, business metric for the journey | Correctness of rare paths |

## Journey scenarios

For each journey, run at least:

- Ordinary success with realistic data.
- Validation failure: field-level messages visible next to the fields, focus
  moved to the first error, nothing persisted.
- Authorization failure: correct status, no data leaked in the body, the UI
  explains next steps.
- Empty and first-use states.
- Slow and failing dependency: loading indicator, timeout message, retry that
  does not duplicate side effects (idempotency key honored).
- Conflict: concurrent edit produces the documented conflict response and a
  recoverable UI.
- Navigation and refresh mid-journey: state restored or safely discarded.

## Evidence rules

- Name the environment, revisions of every deployed layer, and the test
  command or script for each run.
- Store artifacts (traces, screenshots, reports) where reviewers can open them
  after the pipeline run expires.
- Report unavailable levels explicitly, for example "integrated journey not
  run: shared environment unavailable; contract tests and component tests
  passed".
- Never report a run with mocked network calls as an integrated journey.

## Record

Fill the scenario table in the [journey contract](../assets/journey.md.template)
with one row per scenario and the evidence link per level.

## Sources

- [Playwright best practices](https://playwright.dev/docs/best-practices)
- [Testing Library guiding principles](https://testing-library.com/docs/guiding-principles)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [WAI-ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/)
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0)
