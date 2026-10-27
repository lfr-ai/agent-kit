# Delivery pipeline guide

Verified as of 2026-10-27. This guide maps delivery concerns to the reference
or asset that covers them, and to the neighboring skill that owns the rest.

## Ownership

| Concern | Owner |
| --- | --- |
| Pipeline shape, build once and promote by digest, environments, OIDC deploy identity, deployment strategies, rollback, release gates, delivery metrics | `kit-delivery-pipelines` (this skill) |
| Workflow security: triggers, token permissions, untrusted input, action pinning | `kit-ci-review` |
| SBOM, provenance policy, dependency admission, lockfiles | `kit-supply-chain` |
| Release readiness: versioning, changelog, tags, published releases | `kit-release` |
| Image build quality and runtime hardening | `kit-containers` |
| SLIs, SLOs, burn-rate alerts, dashboards | `kit-observability` |
| Infrastructure plans and what-if previews | `kit-terraform-validation`, `kit-azure-validation` |
| Cross-layer infrastructure review and infra recovery | `kit-infra-review` |
| Schema evolution and data migrations | `kit-database-migrations` |
| Reverse proxies, ingress, Gateway API routing | `kit-edge-networking` |

## Map

| Question | Read | Copy |
| --- | --- | --- |
| How should CI and CD be split, cached, and bounded? | [pipeline architecture](pipeline-architecture.md) | [CI](../assets/workflows/ci.yml.template) |
| Who may deploy where, with which identity? | [environments and approvals](environments-and-approvals.md) | [environment matrix](../assets/environments.md.template) |
| How should traffic move to a new version? | [deployment strategies](deployment-strategies.md) | [Container Apps CD](../assets/workflows/cd-container-apps.yml.template), [App Service slots CD](../assets/workflows/cd-app-service-slots.yml.template), [reusable deploy](../assets/workflows/reusable-deploy.yml.template) |
| Which identity, registry, and traffic primitive on Azure, AWS, or Google Cloud? | [cloud targets](cloud-targets.md) | [Amazon ECS CD](../assets/workflows/cd-aws-ecs.yml.template), [Cloud Run CD](../assets/workflows/cd-gcp-cloud-run.yml.template) |
| What if it goes wrong? | [rollback and recovery](rollback-and-recovery.md) | [rollback workflow](../assets/workflows/rollback.yml.template), [runbook](../assets/runbook.md.template) |
| Which gates, in which order, and how do we measure delivery? | [quality gates and metrics](quality-gates-and-metrics.md) | [deploy gate checklist](../assets/deploy-gate-checklist.md.template), [DORA metrics script](../assets/dora-metrics.py.template) |
| Kubernetes with a GitOps controller? | [GitOps](gitops.md) | none; promote by pull request |
| Fixed release windows? | [rollback and recovery](rollback-and-recovery.md) for hotfix rules | [release train](../assets/release-train.md.template) |

## The checker

[check_delivery_workflow.py](../assets/check_delivery_workflow.py) reads
workflow YAML (it needs PyYAML) and reports deploy-job hazards:

| Rule | Finding | Typical fix |
| --- | --- | --- |
| `deploy-needs` | deploy job without `needs` | depend on the build, test, or verify job |
| `deploy-cancel` | `cancel-in-progress: true` on a deploy job or its workflow | scope cancellation to pull requests; queue deploys |
| `deploy-timeout` | deploy job without `timeout-minutes` | set it above bake time plus rollback |
| `oidc-permission` | `azure/login`, `aws-actions/configure-aws-credentials`, or `google-github-actions/auth` without `id-token: write` | grant it on the job; remove stored credentials |
| `mutable-image` | image by tag in a deploy job | pass `name@sha256:...` from CI |
| `rebuild-in-deploy` | build command or build action in a deploy job | promote the artifact CI built |

```text
python check_delivery_workflow.py .github/workflows
python check_delivery_workflow.py .github/workflows --skip-environment=-plan$
python check_delivery_workflow.py --self-test
```

Exit 0 means no findings, 1 means findings, 2 means bad input, a bad option,
or no PyYAML. It is a heuristic: it does not evaluate expressions, follow
reusable workflows, or open composite actions, so a clean run is necessary,
not sufficient. Pass `--login-action` for other OIDC login actions,
`--build-pattern` for other build tools, and `--ignore <rule>` only with a
written justification.

## Limits

These files describe GitHub Actions, Azure, AWS, and Google Cloud behavior
verified on the date above. Templates are syntax-checked here but never run
against a real subscription, account, project, or repository by this toolkit;
adopt them in a non-production environment first.
