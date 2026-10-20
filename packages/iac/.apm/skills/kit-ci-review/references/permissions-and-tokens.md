# Workflow permissions and tokens

Every workflow run receives a `GITHUB_TOKEN` whose scopes come from the
repository or organization default unless the workflow narrows them. Treat the
default as unknown: declare permissions explicitly so the file, not a settings
page, is the reviewed source of truth.

## Rules

1. Declare a top-level `permissions:` block in every workflow. Start from
   `contents: read` (or `{}` for workflows that only call reusable workflows)
   and grant more only where a job needs it.
2. Grant write scopes at the job level, not the workflow level, so a lint or test
   job never inherits a publishing job's privileges.
3. Never use `permissions: write-all` or `read-all`. Name each scope.
4. Grant `id-token: write` only to jobs that exchange an OIDC token with a cloud
   provider or sign an attestation. The scope does not grant write access to
   repository resources; it permits requesting a signed identity token.
5. When a workflow declares any scope, every unlisted scope becomes `none`.
   Review additions carefully: a job that lists only `packages: write` loses
   `contents: read`, so checking out a private repository then fails.
6. Prefer the `GITHUB_TOKEN` over personal access tokens. When a cross-repository
   token is unavoidable, use a GitHub App installation token scoped to the target
   repositories and the minimal permissions, minted per job.

## Scope map for common jobs

| Job | Minimal scopes |
| --- | --- |
| Checkout, lint, unit test | `contents: read` |
| Upload SARIF to code scanning | `contents: read`, `security-events: write` |
| Comment on a pull request | `contents: read`, `pull-requests: write` |
| Push a container image to GHCR | `contents: read`, `packages: write` |
| Cloud login with OIDC | `contents: read`, `id-token: write` |
| Build provenance attestation | `contents: read`, `id-token: write`, `attestations: write` |
| Create a release | `contents: write` |

## OIDC instead of stored cloud secrets

OpenID Connect replaces long-lived cloud credentials with a short-lived token
that the cloud provider trusts only for a specific repository, branch,
environment, or pull request subject.

- Configure the cloud trust (for example an Entra ID federated credential or an
  AWS IAM role trust policy) with the narrowest subject claim. Prefer
  `repo:<owner>/<repo>:environment:<name>` for deployments so that only jobs
  bound to that protected environment can assume the identity.
- Do not trust `pull_request` subjects for identities that can change
  production; fork pull requests cannot obtain OIDC tokens for the base
  repository, but same-repository branches can.
- Use separate identities for plan (read) and apply (write) where the provider
  supports it.
- Customize the subject claim template only through the documented REST API and
  record the change in review evidence.

## Environments as approval gates

- Bind deploy and publish jobs to an environment with required reviewers,
  a deployment branch or tag policy, and (where available) a wait timer.
- Store deployment secrets as environment secrets so they are released only
  after the environment's protection rules pass.
- Prevent self-review when the reviewer list contains the person who triggered
  the run.

## Review checklist

- [ ] Top-level `permissions:` present and minimal.
- [ ] Every job that writes declares only the scopes it uses.
- [ ] `id-token: write` appears only on jobs that log in to a cloud or attest.
- [ ] Cloud trust subjects reference an environment or protected ref.
- [ ] Deploy jobs reference a protected environment.

Run [the workflow checker](../assets/check_workflow_permissions.py) to find
missing top-level permissions and `write-all` grants mechanically.

## Sources

- <https://docs.github.com/en/actions/reference/security/secure-use>
- <https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token>
- <https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect>
- <https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment>
