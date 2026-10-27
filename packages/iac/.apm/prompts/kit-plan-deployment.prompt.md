---
description: Plan or review a deployment pipeline that promotes one immutable artifact through gated environments with rollback.
argument-hint: Service and target, e.g. "orders API to Container Apps in dev, test, and prod"
agent: agent
---

# Plan a deployment pipeline

Design delivery so the exact artifact that passed verification is the one
promoted to production, every promotion is gated, and rollback is rehearsed.

## Input

- The user-supplied argument names the service, the hosting target, and the
  environments. Ask for the cloud, approval requirements, and acceptable
  downtime when they are not stated and cannot be read from existing workflows.

## Procedure

1. Load [kit-delivery-pipelines](../skills/kit-delivery-pipelines/SKILL.md) and
   read the existing workflows, environments, and deploy scripts first.
2. Build once: one CI job builds, tests, scans, and pushes the artifact, then
   records its immutable digest. Deploy jobs never rebuild.
3. Define each environment with its protection rules: required reviewers,
   allowed branches or tags, secrets versus variables, and the cloud identity
   it may assume through OIDC federation, never stored keys.
4. Choose the rollout strategy per environment (rolling, blue-green, canary,
   slots, or revisions with traffic weights) and the health and SLO signals
   that promote or roll back automatically.
5. Sequence database changes with expand and contract so old and new versions
   run side by side during the rollout.
6. Set concurrency so superseded pull request runs cancel but deployments never
   cancel each other, and give every job a timeout.
7. Add a manual rollback workflow that redeploys a previous digest or shifts
   traffic back, and a post-deploy smoke check.
8. Hand workflow security review to the `kit-ci-review` skill, plan or what-if
   review to `kit-terraform-validation` or `kit-azure-validation`, provenance
   and SBOMs to the shared `kit-supply-chain` skill, and alerts to
   `kit-observability`.
9. Run the skill's delivery-workflow checker and the CI review checker on the
   changed workflows, then the project completion gate.
10. Record how to measure deployment frequency, lead time, change failure
    rate, and time to restore.

## Acceptance gates

- [ ] Production receives the same digest that passed every earlier stage.
- [ ] Every deploy job needs the build and test jobs and runs in a protected environment.
- [ ] Cloud access uses OIDC federation scoped per environment.
- [ ] Deployments never cancel each other, and every job has a timeout.
- [ ] Rollback is a documented, tested workflow, not an ad hoc rebuild.

## Output

The pipeline stages and environments table, the rollout and rollback plan,
files changed, checker results, and open risks.
