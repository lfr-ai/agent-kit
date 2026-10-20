# Stage 6: Verify

Verify proves the change does what the requirements say, in an environment as
close to production as the project allows, and records evidence another person
can reproduce.

## Entry criteria

- All task boxes ticked or deferred; checker passes.
- The build artifact or branch under verification is identified exactly
  (commit, version or image digest).

## Activities

1. Copy [the verification template](../assets/verification.md.template) to
   `verification.md`.
2. For each scenario of each active requirement, record one row: requirement
   identifier, scenario name, method (automated test, manual check, contract
   test, monitoring query), the exact command or steps, and the observed
   outcome.
3. Run the full automated suite at the identified revision. Record the command,
   the pass/fail counts and the duration. Do not reuse results from an older
   revision.
4. Check the non-functional targets stated in the design (latency, memory,
   throughput, accessibility). Record measurement method and numbers.
5. Compare the implementation with `design.md`. List each deviation and why it
   is acceptable, or reopen Plan.
6. Confirm the proposal's impact items: documentation updated, configuration
   documented, migrations reversible, dashboards and alerts adjusted.
7. Re-run removed-requirement checks: behavior marked `Change: remove` is
   actually gone or explicitly disabled.
8. Set `Result: pass` only when every row passed. Otherwise set
   `Result: fail`, list the failing rows, and return to Apply.
9. Obtain owner acceptance and set `Status: verified`.

## Evidence quality

- Commands are ready to copy and paste and include required flags and environment
  variables (never secrets).
- Manual checks name the account role, data set and the exact observation.
- Screenshots or logs are attached or linked with a retention that outlives
  the review.
- "Works on my machine" is not evidence; name the environment.

## Exit criteria

- Every active scenario has a passing row.
- Full-suite results are recorded for the verified revision.
- Deviations are explained and accepted.
- `Result: pass` and owner acceptance are recorded.

## Acceptance gate

```text
python assets/check_spec_change.py <changes>/<id> --trace
```

exits 0 with `Status: verified`; the checker requires every box ticked and
`Result: pass`. Continue with [archive](stage-archive.md).

## Anti-patterns

- Verifying only the happy-path scenario.
- Marking `pass` with known failures "to be fixed later".
- Evidence that cannot be traced to a specific revision.

## Sources

- [pytest: How to invoke pytest](https://docs.pytest.org/en/stable/how-to/usage.html)
- [Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/)
