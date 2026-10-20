---
description: Deliver a feature across backend, frontend, and infrastructure contract first, with a rollout order, mixed-version checks, and an integrated journey test.
argument-hint: The user journey to deliver, e.g. "users export invoices as CSV"
agent: agent
---

# Deliver a fullstack feature

Ship one user journey across every layer it touches, in the order those layers
deploy, with the shared contract settled before either side implements it.

## Input

- The user-supplied argument describes the user journey. Ask for the actor,
  entry point, and failure states the user can see if they are not clear.

## Procedure

1. Load [kit-fullstack-workflow](../skills/kit-fullstack-workflow/SKILL.md) and
   follow its procedure, using its journey contract, contract change record,
   and rollout plan templates.
2. Write the journey: actor, entry point, steps, success state, and visible
   failure states (invalid, unauthorized, empty, slow, conflicting, offline).
3. Map each involved package, its owner, toolchain, deployment unit, and its
   own instructions; read them before editing.
4. Change the authoritative contract first. Classify each change as additive
   or breaking and settle naming, nullability, pagination, error shape,
   authorization, idempotency, and versioning before implementation.
5. Plan the rollout: infrastructure before code that needs it, expand before
   migrate before contract, producers before consumers, removal last. Give
   every forward step a rollback step.
6. Provision infrastructure only through reviewed plans or previews; secrets
   are referenced, never written into code or examples.
7. Implement the backend slice against the contract, applying the backend
   package skills `kit-api-contracts`, `kit-python-service`, and
   `kit-database-migrations` where relevant.
8. Implement the frontend slice against the contract, not against current
   backend behavior, applying the frontend package skills `kit-react-feature`,
   `kit-state-data`, and `kit-forms` where relevant.
9. Add contract tests on both sides that fail when either drifts.
10. Run the journey against real or locally composed services. Mocked runs are
    not end-to-end evidence.
11. Check mixed-version compatibility for every intermediate rollout step:
    old client with new server and new client with old server.
12. When delegating, split by deployment unit; workers never change the
    contract on their own.

## Acceptance gates

- [ ] The contract changed first and every layer builds against that version.
- [ ] Breaking changes have a versioning or expand-and-contract plan.
- [ ] Each layer passes its own gates and contract tests pass on both sides.
- [ ] The integrated journey ran and its evidence is recorded.
- [ ] Rollback is documented per step.

## Output

The journey contract, the contract change record, the rollout plan as a table
(step, layer, rollback, health signal), per-layer gate results, journey
evidence, and any layer that could not be verified, named explicitly.
