# Cross-stack guide

Quality gates, failure modes and recovery for fullstack delivery. Detailed
practice lives in [contract-first design](contract-first.md),
[sequencing](sequencing.md), [infrastructure coordination](iac-coordination.md)
and the [verification matrix](verification-matrix.md).

## Ownership

Separate backend, frontend, contract and infrastructure ownership. The
coordinator owns the journey and the sequence; each layer owner owns their
gates. Contract changes go through the contract owner even when one person
implements every layer. Secrets and deployment configuration stay in the
consumer packages and the secret store.

## Quality gates

| Gate | Pass condition |
| --- | --- |
| Contract first | The reviewed contract change merged before dependent implementation |
| Single source | Clients, fixtures and server validation derive from the same contract version |
| Error shape | Every error uses the documented problem shape with stable types |
| States | Loading, empty, invalid, unauthorized, timeout, conflict and recovery defined and rendered |
| Accessibility | Keyboard and screen-reader behavior hold in every state, including failures |
| Infrastructure | Preview reviewed, applied before dependent code, verified from the consumer |
| Compatibility | Every rollout step works with the neighboring versions |
| Journey | Integrated journey evidence at named revisions |
| Rollback | Documented per step, in reverse order |

## Failure modes

- **Contract drift.** Backend changed a field without updating the contract;
  the frontend built against the document breaks in integration. Detect with
  provider contract tests and a generation drift check in CI.
- **Mock-only confidence.** All tests pass against hand-written mocks that
  describe a shape the server never sends. Detect by validating fixtures
  against the specification.
- **Silent client fallback.** The frontend papers over a missing field with a
  default, hiding a server regression. Fix the contract or server; surface
  the error.
- **Configuration race.** Code deployed before the setting or permission it
  needs; the first requests fail. Detect by verifying infrastructure from the
  consuming identity before merging dependent code.
- **One-way compatibility.** New frontend requires the new backend, but the
  backend rollback restores the old one. Detect with the compatibility matrix;
  gate the frontend behind a switch.
- **Partial rollout reported as done.** One layer released, the feature
  switched off, and the hand-off says complete. Report the actual state per
  layer.

## Recovery

1. If layers disagree, fix the authoritative contract first, regenerate
   clients and fixtures, then fix the implementations; do not add a silent
   client fallback.
2. If the live service is unavailable, keep contract fixtures and component
   tests, and report the missing journey check by name.
3. Roll back in the documented reverse order so a restored client is never
   paired with an incompatible server.
4. After an incident, add the missing level from the verification matrix as a
   permanent check.

## Assets

- [Journey contract](../assets/journey.md.template)
- [Contract change record](../assets/contract-change.md.template)
- [Rollout plan](../assets/rollout-plan.md.template)
- [OpenAPI resource template](../assets/openapi.yaml.template)

## Sources

- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0)
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [Playwright best practices](https://playwright.dev/docs/best-practices)
