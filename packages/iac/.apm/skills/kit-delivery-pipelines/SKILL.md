---
name: kit-delivery-pipelines
description: Use when designing CI/CD delivery with build-once promotion, environments, rollout, and rollback.
license: MIT
---

# Design and review delivery pipelines

Delivery is the path from a merged commit to a running, observable,
reversible release. The rule that holds it together: build one immutable
artifact once, then promote that exact digest through every environment.
Start with the [delivery guide](references/guide.md); it maps each concern to a
reference, a template, or the neighboring skill that owns it.

## Procedure

1. Map the current path: triggers, workflows and jobs, artifact type, registry,
   environments, deploy identity, rollout mechanism, rollback path, and who
   approves. Record it in the [environment matrix](assets/environments.md.template).
2. Separate the stages per [pipeline architecture](references/pipeline-architecture.md):
   CI builds, tests, and attests one artifact per trunk commit; CD only
   verifies and deploys. No deploy job checks out unreviewed code or builds.
3. Make the digest the identity of the release: CI pushes the image, records
   `name@sha256:...`, and attests provenance; CD resolves a tag at most once,
   verifies the attestation, and passes the digest to every environment.
4. Review caching, concurrency, timeouts, and matrix bounds: lockfile-keyed
   caches that never feed the deployable, cancelling concurrency for pull
   requests only, queued (never cancelled) deploys, and `timeout-minutes` on
   every job.
5. Define environments per [environments and approvals](references/environments-and-approvals.md):
   one GitHub environment per target, branch rules limited to the trunk,
   required reviewers with self-review prevention for production, and one
   OIDC identity per environment whose trust names that environment's
   subject (Azure federated credential, AWS role trust policy, or Google
   Workload Identity Federation; see [cloud targets](references/cloud-targets.md)).
   No long-lived cloud credentials in GitHub.
6. Choose the rollout strategy per [deployment strategies](references/deployment-strategies.md)
   and the target's primitive per [cloud targets](references/cloud-targets.md):
   revisions and traffic weights (Container Apps, Cloud Run), slots and swap
   (App Service), the ECS canary, linear, or blue/green strategy, weighted
   Lambda aliases, or a progressive-delivery controller on Kubernetes. Write
   the abort signals and thresholds before the rollout and get the SLO
   signals from `kit-observability`.
7. Check every data, schema, and event change for compatibility with both
   running versions (expand, migrate, contract); hand the migration plan to
   `kit-database-migrations`.
8. Prove the rollback per [rollback and recovery](references/rollback-and-recovery.md):
   a live rollback target (previous revision at 0%, swapped-out slot, retained
   digest), a decision rule for rollback versus roll forward, and a runbook
   from the [runbook template](assets/runbook.md.template) exercised in a lower
   environment.
9. Order the gates per [quality gates and metrics](references/quality-gates-and-metrics.md):
   cheap to expensive, blocking or clearly informational, required checks that
   path filters cannot skip, smoke checks before and after traffic moves.
   Workflow security goes to `kit-ci-review`, provenance and dependency
   policy to `kit-supply-chain`, and release readiness to `kit-release`.
10. When proposing workflows, adapt the templates instead of writing from
    memory: [CI](assets/workflows/ci.yml.template),
    [Container Apps CD](assets/workflows/cd-container-apps.yml.template),
    [App Service slots CD](assets/workflows/cd-app-service-slots.yml.template),
    [reusable deploy](assets/workflows/reusable-deploy.yml.template),
    [rollback](assets/workflows/rollback.yml.template),
    [Amazon ECS CD](assets/workflows/cd-aws-ecs.yml.template), and
    [Cloud Run CD](assets/workflows/cd-gcp-cloud-run.yml.template). Replace
    every `PIN_FULL_COMMIT_SHA` with a reviewed full commit SHA.
11. Run the [delivery checker](assets/check_delivery_workflow.py) on the
    changed workflows and record its output:

    ```text
    python check_delivery_workflow.py .github/workflows
    python check_delivery_workflow.py --self-test
    ```

    It exits 0 when clean, 1 with findings (`path:line: [rule] message`), and 2
    for unreadable input, a bad option, or missing PyYAML. Use
    `--skip-environment=<regex>` for environments that only scope read-only
    credentials, and `--ignore <rule>` only with a written reason.
12. For production promotions, fill the
    [deploy gate checklist](assets/deploy-gate-checklist.md.template); for
    fixed release windows, use the [release train](assets/release-train.md.template)
    and keep its hotfix rules.
13. When Kubernetes runs a GitOps controller, follow [GitOps](references/gitops.md):
    promotion and rollback are reviewed changes to the environment overlay,
    and drift is alerted.
14. Measure delivery per service with the
    [DORA metrics script](assets/dora-metrics.py.template) from exported
    deployment records plus incident data, and read it next to the SLO.
15. Hand changes to repository settings, environments, identities, and any
    real deployment to the named operator. Never trigger a deploy, approve an
    environment, or run a rollback against a shared environment from an
    authoring session.

## Acceptance gates

- [ ] One artifact per trunk commit, deployed everywhere as `name@sha256:...`
      with a verified provenance attestation; no deploy job builds.
- [ ] Every deploy job `needs` the job that built, tested, or verified the
      artifact, has `timeout-minutes`, and never cancels in progress.
- [ ] Cloud access uses OIDC with an environment-scoped subject and
      `id-token: write` only on the jobs that need it.
- [ ] Production has required reviewers, self-review prevention, trunk-only
      branch rules, and no administrator bypass.
- [ ] The rollout strategy, abort signals, and thresholds are written; smoke
      checks run before traffic moves and after promotion.
- [ ] A rollback target exists, the rollback is a traffic switch or a
      redeploy of an attested digest, and the runbook was exercised.
- [ ] Schema and data changes are compatible with both running versions.
- [ ] The delivery checker reports no findings, or each one has an
      owner-approved justification.
- [ ] Delivery metrics, when reported, come from deployment records and
      incident data for one service.

## Out of scope

Workflow and template checks are static. They do not prove that environments,
protection rules, federated credentials, or Azure resources are configured as
described; verify those in the consumer's settings and a non-production
deployment before relying on them.
