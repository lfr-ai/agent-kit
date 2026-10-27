# APIOps: gateway configuration as code

Verified as of 2026-10 against the sources listed at the end. The workflow
template is [apiops.yml](../assets/github/apiops.yml.template); the
infrastructure templates are [main.bicep](../assets/bicep/main.bicep.template),
[apim.bicep](../assets/bicep/apim.bicep.template),
[api.bicep](../assets/bicep/api.bicep.template), and
[main.bicepparam](../assets/bicep/main.bicepparam.template).

## Principles

1. Git is the source of truth for the instance, APIs, products, named values
   (references, not secret values), backends, diagnostics, and every policy.
2. Every change goes through a pull request with automated gates; the same
   commit is promoted from environment to environment.
3. No portal click-ops in shared environments. The portal and test console
   are for reading and diagnosis; a change made there is drift and is
   overwritten by the next deployment or reverted deliberately.
4. Environments differ only in parameter files. Policy XML and OpenAPI files
   are identical everywhere; per-environment values are named values.
5. Deployment identities are federated (OIDC) and least-privileged; no
   stored client secrets and no management keys in the pipeline.

## Repository layout

```text
apim/
  main.bicep                    composition root
  modules/
    apim.bicep                  instance, identity, logger, diagnostics, global policy
    api.bicep                   one versioned API: version set, API, backend, named values, product
  parameters/
    dev.bicepparam
    prod.bicepparam
  policies/
    global.xml
    orders-api.xml
    fragments/                  shared fragments with named owners
  openapi/
    orders.v1.json              copied from the contract owner's release
    released/orders.v1.json     last description released to consumers
tools/
  check_apim_policy.py          from kit-api-gateway
  compare_openapi.py            from kit-api-contracts
.github/workflows/apiops.yml
```

The OpenAPI document is produced and versioned by the service that owns the
contract (`kit-api-contracts`). The gateway repository imports a released copy
(by commit, package, or artifact digest); it never edits operations.

## Two tools, two jobs

| Concern | Tool | Why |
| --- | --- | --- |
| Instance, network, identity, loggers, diagnostics, role assignments | Bicep (or Terraform `azurerm`) | Long-lived infrastructure with what-if/plan review |
| APIs, policies, products, named values, backends | Bicep in this skill's templates, or APIOps CLI artifacts | Changes often; must be reviewed as text |

- Bicep with `loadTextContent` keeps policy XML and OpenAPI as separate,
  reviewable files and deploys everything in one what-if-able unit. The
  limit is 131,072 characters per loaded file; split large policies into
  fragments.
- The APIOps CLI (an open-source Microsoft tool) extracts an existing
  instance into artifact files and publishes them, with a dry-run mode. It
  suits teams migrating from portal-managed instances: extract once, commit,
  and from then on publish only from Git. Choose one publisher per resource;
  two tools writing the same API cause flapping.
- Terraform: the `azurerm` provider has `azurerm_api_management*` resources
  for the same objects; use `azapi` only for properties not yet in `azurerm`.
  Keep the same file layout and gates (`kit-terraform-validation`).

## Pull request gates

Run in order, without cloud credentials:

1. OpenAPI lint with the project's linter and the contract rules of
   `kit-api-contracts`.
2. Breaking-change gate: compare the candidate description with
   `released/` using `compare_openapi.py` (JSON descriptions). A breaking
   change fails unless it ships as a new version (`orders-v2`) with a
   deprecation plan for v1.
3. Policy gate:
   `python3 tools/check_apim_policy.py --require-auth --require-quota apim/policies`.
   Each finding is fixed or disabled by rule with a written reason in the pull
   request.
4. Bicep build, `bicep lint`, and `build-params` for every parameter file.
5. Policy XML parsing is part of the policy gate; a policy that fails
   to parse fails the build before Azure rejects it.

With credentials (a read-only identity, `<env>-preview` environment):

1. `az deployment group what-if` per environment; upload the result as an
   artifact for the approver.
2. Reject what-if output that deletes an API, product, or subscription the
   change did not intend to remove (`kit-azure-validation` covers what-if
   review in depth).

## Promotion

- Build once: the commit that passed the gates is the input to every
  environment. Do not regenerate policies or re-download OpenAPI per stage.
- Order: dev, then (optionally) test, then prod. Each production deployment
  waits for a required reviewer on the GitHub environment who reads the
  uploaded what-if.
- After each deployment run a smoke test through the gateway: an anonymous
  call to a protected operation must return 401; a call with a test
  subscription and token must return 200 from the health or a read operation.
  Run consumer contract tests where they exist (`kit-api-testing`).
- Introduce risky API changes as a new revision, test it with `;rev=N`, then
  make it current in a follow-up deployment. Roll back by making the previous
  revision current or by redeploying the previous commit.
- Product, subscription approval, and portal changes follow the same path.
  Subscriptions themselves (consumer keys) are runtime data: issue them
  through the portal or an onboarding workflow, not through Bicep.

## Secrets in the pipeline

- The pipeline never sees secret values. Bicep passes Key Vault secret URIs
  (without version) to named values; the instance identity reads them.
- Parameter files contain only non-secret values. A secret in a
  `.bicepparam` file is a defect even if the repository is private.
- `azure/login` uses `client-id`, `tenant-id`, and `subscription-id` with
  `id-token: write`; federated credentials are bound to GitHub environments so
  only approved jobs can deploy.
- Pin every action to a full commit SHA (`kit-ci-review`).

## Drift

- Schedule a what-if (or an APIOps CLI extract and diff) against production
  and alert on differences.
- When drift is found, either revert it by redeploying from Git or capture it
  in a pull request; never leave both versions alive.
- Lock down portal write access in production to the platform team; everyone
  else uses read access and pull requests.

## Delivery ownership

The general continuous-delivery rules (environments, approvals, rollback
strategy, release gates) belong to `kit-delivery-pipelines`; workflow
security review belongs to `kit-ci-review`. This reference covers only what is
specific to the API gateway.

## Sources

- Use DevOps and CI/CD to publish APIs:
  <https://learn.microsoft.com/en-us/azure/api-management/devops-api-development-templates>
- Manage API Management configuration with APIOps CLI:
  <https://learn.microsoft.com/en-us/azure/api-management/how-to-manage-apiops-cli>
- Automated API deployments with APIOps (architecture):
  <https://learn.microsoft.com/en-us/azure/architecture/example-scenario/devops/automated-api-deployments-apiops>
- Bicep `loadTextContent`:
  <https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-functions-files>
- Bicep what-if:
  <https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if>
- Bicep resource reference, `Microsoft.ApiManagement/service/apis`:
  <https://learn.microsoft.com/en-us/azure/templates/microsoft.apimanagement/service/apis>
- Authenticate to Azure from GitHub Actions with OpenID Connect:
  <https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect>
- GitHub Actions environments:
  <https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments>
