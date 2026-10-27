# Environments, approvals, and deployment identity

Verified as of 2026-10-27 against the GitHub Actions, Microsoft Entra, and
Azure Pipelines documentation listed under Sources. Plan availability notes
apply to GitHub Free, Pro, and Team plans; check the current plan matrix
before relying on a protection rule in a private repository.

## What a GitHub environment gives you

A job that names `environment:` becomes a deployment: GitHub records a
deployment object for it, runs the environment's protection rules before the
job starts, and only then releases the environment's secrets and variables to
that job. Use one environment per deployment target (`dev`, `test`,
`production`), not per workflow.

| Protection | What it enforces | Notes |
| --- | --- | --- |
| Required reviewers | up to six users or teams; one approval releases the job | enable "prevent self-review" so the person who triggered the run cannot approve it |
| Wait timer | delay of 1 to 43,200 minutes after the job is triggered | useful as a soak period between environments; not billed |
| Deployment branches and tags | only matching `GITHUB_REF` values may deploy | choose "selected branches and tags" with `main` (and release tags if used); "protected branches only" allows every branch when no branch is protected |
| Administrator bypass | on by default | turn it off for production so emergency changes still leave an approval trail |
| Custom protection rules | GitHub App decides (monitoring, change window) | up to six rules enabled per environment; public preview |

Availability: on GitHub Free, Pro, and Team plans, required reviewers, wait
timers, and admin-bypass settings are available only for public repositories;
deployment branch rules and environment variables also cover private
repositories on Pro and Team. Environment secrets in private repositories need
Pro, Team, or Enterprise.

## Secrets versus variables

| Kind | Put here | Never put here |
| --- | --- | --- |
| Environment variables (`vars`) | client ID, tenant ID, subscription ID, resource group, app name, canary weights, URLs | anything that grants access by itself |
| Environment secrets | the rare credential that has no federated alternative (third-party API keys used during deploy) | cloud credentials when OIDC is possible |
| Repository or organization secrets | values that every environment may read | production-only credentials |

Identifiers such as the Entra client ID are not secrets: they cannot be used
without a token issued to the trusted subject. Keeping them in `vars` keeps
them visible for review. Workflows on self-hosted runners are not isolated by
environments; treat environment secrets there with the same care as
repository secrets.

## OIDC to Azure without long-lived credentials

1. Create one Entra application or user-assigned managed identity per
   environment (`orders-deploy-dev`, `orders-deploy-test`,
   `orders-deploy-prod`).
2. Add a federated credential with issuer
   `https://token.actions.githubusercontent.com`, audience
   `api://AzureADTokenExchange`, and a subject bound to the environment:
   `repo:<owner>/<repo>:environment:<name>`. Any `:` inside a value is encoded
   as `%3A`. When a job names an environment, the subject contains the
   environment and not the branch, so the branch restriction lives in the
   environment's deployment-branch rule.
3. Repositories created after 2026-07-15 (and repositories renamed or
   transferred after that date) emit the immutable subject form
   `repo:<owner>@<owner-id>/<repo>@<repo-id>:environment:<name>`; older
   repositories keep the name-only form unless they opt in. Match the form the
   repository actually emits.
4. Grant the identity the narrowest Azure role on the narrowest scope that the
   deploy needs (the app, not the subscription). Assign roles through
   infrastructure code reviewed with `kit-azure-validation` or
   `kit-terraform-validation`.
5. In the workflow, grant `id-token: write` on the deploy job only and log in
   with `azure/login` using `client-id`, `tenant-id`, and `subscription-id`
   from environment variables. No client secret, certificate, or publish
   profile is stored in GitHub.

Constraints worth knowing: an application or user-assigned managed identity
holds at most 20 federated credentials; issuer and subject must match the
token exactly and wildcards are not supported; a wrong subject is accepted at
creation time and only fails at token exchange, silently from the workflow's
point of view. Test a new credential in `dev` before relying on it.

Pull request workflows must not reach a deployment identity: the
`pull_request` subject (`repo:<owner>/<repo>:pull_request`) is only issued to
jobs without an environment, so never federate it with a role that can write.

## Approval design

- Approve the artifact, not the code: the approval screen should show the
  digest, the commit range since the last production deploy, test results,
  and the gate checklist (see the deploy gate template).
- Put the approval as late as possible: after dev and test have run the same
  digest, before production traffic moves. A wait timer between test and
  production gives automated signals time to fire.
- Approvers must be able to judge risk; one approval from a release-approver
  team is enough when self-review is prevented. More approvers rarely add
  safety and always add delay.
- Record emergency changes through the same path with a shorter wait; never
  create a side channel that bypasses environments.

## Azure DevOps equivalents (consumer owned)

When a consumer runs Azure Pipelines instead, the same model maps to:
environments with approvals and checks configured outside YAML by the resource
owner; check categories that run in order (static checks such as branch
control and required template, pre-check approvals, dynamic checks such as
approval, Azure Monitor alert queries, business hours, REST or Azure Function
calls, post-check approvals, then exclusive lock); and service connections
using workload identity federation instead of secrets. The consumer owns that
configuration; this skill only reviews that it matches the matrix in the
environments template.

## Review checklist

- [ ] One environment per target, with branch rules limited to the trunk.
- [ ] Production has required reviewers, self-review prevention, and no
      administrator bypass.
- [ ] Every cloud login uses OIDC with an environment subject; no cloud
      secrets or publish profiles exist in the repository or environment.
- [ ] Each environment has its own identity with an app-scoped role.
- [ ] `id-token: write` appears only on jobs that log in to the cloud or
      attest.
- [ ] Environment settings match the environments template, and changes to
      them are reviewed.

## Sources

- <https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments>
- <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure>
- <https://docs.github.com/en/actions/reference/security/oidc>
- <https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust>
- <https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals>
- <https://docs.github.com/en/rest/deployments/deployments>
