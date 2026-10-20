---
name: kit-fullstack-workflow
description: Use when coordinating a change across backend and frontend contracts.
license: MIT
---

# Deliver a feature end to end, contract first

A fullstack feature is done when a real user journey works across every layer
it touches, in the order those layers will actually be deployed. Green tests in
one package prove that package, not the feature. Sequence the work so the
shared contract is settled first and every intermediate deployment stays
compatible.

## Procedure

1. **Frame the journey.** Write the user outcome and the end-to-end journey in
   the [journey contract](assets/journey.md.template): actor, entry point,
   steps, success state and the failure states the user can see (invalid,
   unauthorized, empty, slow, conflicting, offline).
2. **Map the layers and owners.** List each package or repository involved
   (API contract, backend services, frontend apps, infrastructure, data
   migrations), its owner, its toolchain and its deployment unit. Read each
   package's own instructions before changing it.
3. **Settle the contract first.** Change the authoritative contract
   (specification, schema or typed interface) before either side implements
   it, following [contract-first design](references/contract-first.md). Start
   from the [OpenAPI template](assets/openapi.yaml.template) for new HTTP
   resources. Classify each change as additive or breaking and record it in
   the [contract change record](assets/contract-change.md.template).
4. **Review the contract** with backend, frontend and consumer owners. Settle
   naming, nullability, pagination, error shape, authorization, idempotency and
   versioning now; changing them after implementation doubles the work.
5. **Plan the sequence** with [sequencing](references/sequencing.md): expand
   before migrate before contract; infrastructure prerequisites before code
   that needs them; producers before consumers; removal last. Write it in the
   [rollout plan](assets/rollout-plan.md.template) with a rollback step for
   every forward step.
6. **Provision infrastructure** through reviewed plans or previews, following
   [infrastructure coordination](references/iac-coordination.md): new
   resources, configuration keys, secrets references, permissions and network
   rules land before the code that reads them.
7. **Implement the backend slice** against the contract: boundary validation,
   domain behavior, persistence, error mapping and contract tests that fail
   when the implementation drifts from the specification.
8. **Implement the frontend slice** against the contract, not against the
   backend's current behavior: generated or typed client, every visible state
   from step 1, accessible interactions, and component tests with contract
   fixtures.
9. **Integrate.** Run the journey against real deployed or locally composed
   services. Mocked clients prove the frontend; contract tests prove the
   seam; only the integrated journey proves the feature.
10. **Verify with the [verification matrix](references/verification-matrix.md)**:
    each layer's own gates, the contract tests, the journey, accessibility, and
    old-client/new-server plus new-client/old-server compatibility during the
    rollout window.
11. **Roll out in plan order**, checking the health signal named for each step
    before the next. Keep the previous version deployable until the contract
    phase completes.
12. **Hand off** with the journey evidence, the contract record, the rollout
    plan status and any layer that could not be verified, named explicitly.

## Delegation

When separate context helps, split work by deployment unit, not by file type:
one worker for the contract and backend boundary, one for the frontend, one
for infrastructure review. Give each worker the settled contract, its owned
paths, its gates and the stop condition. Workers never change the contract on
their own; contract changes return to the coordinator.

## Acceptance gates

- [ ] The authoritative contract changed first and every layer builds against
      that version.
- [ ] Every contract change is classified additive or breaking; breaking
      changes have a versioning or expand-and-contract plan.
- [ ] Error responses share one documented shape, and the frontend renders each
      failure state named in the journey.
- [ ] Infrastructure changes were previewed and applied before dependent code;
      no secret values appear in code, contract examples or logs.
- [ ] Each layer passes its own gates; contract tests pass on both sides.
- [ ] The integrated journey ran against real services and its evidence is
      recorded; mocked runs are not reported as end-to-end.
- [ ] Mixed-version compatibility holds for every intermediate rollout step.
- [ ] Rollback is documented per step and does not pair a restored client with
      an incompatible server.

## Stop and escalate

- Two layers disagree about the contract: stop both, fix the authoritative
  contract, regenerate, then continue.
- A step has no safe rollback: add a compatibility window or a feature switch
  before proceeding.
- A layer cannot be verified in any environment: report the gap; do not
  substitute a mocked result.

Quality gates, failure modes and recovery are in the
[cross-stack guide](references/guide.md).
