# Microsoft Foundry: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default. They
deliberately **do not restate** these 2025-09-01 defaults: unrestricted
outbound access, dynamic throttling off, Microsoft-managed encryption keys, no
user-owned storage, the default content filter
(`raiPolicyName`) and the service's model version-upgrade option
(`versionUpgradeOption`). `publicNetworkAccess` is always declared: `Disabled`
unless a dev or test caller without a private endpoint sets
`allowPublicNetworkAccess`, which also declares `networkAcls` with
`defaultAction: Deny` and the `allowedIpRanges` (an empty list denies all
public traffic) unless `allowAllPublicClients` sets `defaultAction: Allow`.
`disableLocalAuth: true` is declared because keys are enabled
by default, and
`enabled: true` on each diagnostic-setting entry because the API requires it.
`format: OpenAI` is this composition's deployment default, not an ARM default.

Because these are not declared, a source deployment does not revert drift if
someone changes them later. Enforce the security settings with Azure Policy
(local authentication disabled, public network access disabled in staging and production).
Read `versionUpgradeOption` back after the first deployment and follow the
[model retirement schedule](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-retirements);
pin an upgrade option only as a reviewed change.

## Operator gates and ownership

- The app identity already exists. Pass its **object (principal) ID**; the
  application authenticates with the identity's client ID. For the same,
  identically cased resource and principal IDs, Bicep `guid()` and Terraform
  `uuidv5()` produce the same assignment names; still let one tool own an
  environment.
- Roles, from least to broader:
  - `Cognitive Services OpenAI User` (`5e0bd9bd-7b93-4f28-af87-19fc36ad61bd`) on
    the resource: inference for OpenAI models through `openai/v1`. It cannot
    list keys or change deployments, and Microsoft states it grants access to
    OpenAI models only.
  - `Foundry User` (`53ca6127-db72-4b80-b1b0-d745d6d5456d`, formerly
    `Azure AI User`) on the project: Microsoft's documented developer role at
    project scope. Its data actions stay inside the project.
  - If the app only calls existing agents, `Foundry Agent Consumer`
    (`eed3b665-ab3a-47b6-8f48-c9382fb1dad6`) at project or agent scope is
    narrower; replace the project grant as a reviewed change.
  - Non-OpenAI models through the account endpoint need `Cognitive Services
    User` on the resource (broad: all data actions plus `listkeys`) or a custom
    role with `Microsoft.CognitiveServices/accounts/MaaS/*`. Partner and
    community models also need Azure Marketplace permissions. Neither is
    granted here.
- The deploying identity needs role-assignment write access on the resource
  and project (for example a constrained Role Based Access Control
  Administrator assignment). Allow up to five minutes before the first call.
- Register `Microsoft.CognitiveServices`. Confirm the region offers every model,
  version and deployment type you list and that the subscription has quota;
  quota is per subscription, region, model and deployment type. Deployments run
  one at a time because the resource accepts one child operation at a time.
- `name` is also the immutable custom subdomain and project name; changing it
  creates a new resource. Deleted resources stay soft-deleted for 48 hours and
  block the name until purged or recovered.
- For a private endpoint, provide an existing same-region subnet and the three
  existing zones `privatelink.cognitiveservices.azure.com`,
  `privatelink.openai.azure.com` and `privatelink.services.ai.azure.com`, each
  with a VNet link. Clients keep using the public host names, which resolve to
  the private address. With public access disabled, data-plane calls and the
  Foundry portal work only from networks that resolve and route to the
  endpoint. The endpoint is created after the project and deployments, because
  binding earlier fails with `AccountProvisioningStateInvalid`.
- Agent Service network injection (agents in your subnet with your own storage,
  search and Cosmos DB) is out of scope.
- The production lock covers the resource and is inherited by the project,
  deployments and grants. Removing a deployment, the project or a grant in
  production therefore needs a reviewed lock removal. A Bicep incremental
  deployment leaves deployments and grants that left the input in place: remove
  them explicitly.
- The lock does **not** block updates or an actor who may remove locks.
  Terraform destroy removes its own lock first; operator approvals must deny
  unreviewed destroy, replacement and lock removal.
- Diagnostics need an existing Log Analytics workspace (required in
  staging and production). `allLogs` covers `Audit`, `RequestResponse`, `Trace`,
  `AzureOpenAIRequestUsage` and `ManagedNetworkEvent`; the last two carry an
  export charge, and ingestion and retention are billed by the workspace. The
  deploying identity needs diagnostic-settings write access on the resource and
  access to the workspace. Delete the setting before deleting or re-creating
  the resource: Azure Monitor can reapply leftover settings to a resource with
  the same ID.
- The guards accept only Azure public-cloud private DNS zones, by exact ARM ID
  shape and casing, and a `Microsoft.Network/virtualNetworks/*/subnets/*`
  subnet ID; the endpoint outputs are public-cloud host names.

## OCR decision

OCR uses the separate [Document Intelligence composition](../document-intelligence/README.md),
not this Foundry resource:

- The Document Intelligence v4.0 (`2024-11-30`) quickstart says: "For Document
  Intelligence access only, create a Document Intelligence resource. You need a
  single-service resource if you intend to use Microsoft Entra authentication."
  The `azure-ai-documentintelligence` SDK README gives the same instruction.
- Least privilege: `Cognitive Services User` on a Foundry resource grants every
  data action on it, including all model inference; on a single-service
  resource it grants Document Intelligence only.
- Separate network isolation, lock, throughput limits and diagnostics per
  workload. The broader Foundry Tools authentication page describes Entra ID for
  multi-service resources in general; the service-specific guidance wins.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**, like every other delivery composition; there is no
azurerm constraint to match, and azapi mirrors the ARM body so the Bicep and
Terraform sources stay comparable property by property. azurerm 5.x has
equivalent resources (`azurerm_cognitive_account`,
`azurerm_cognitive_account_project`, `azurerm_cognitive_deployment`); switching
is a reviewed change with state migration.

API versions: `Microsoft.CognitiveServices` 2025-09-01, the newest GA version
in the local Bicep type index (newer GA versions exist; adopt them once Bicep
ships their types), `Microsoft.Network` 2025-01-01 (same reason), role
assignments 2022-04-01, locks 2020-05-01 and
`Microsoft.Insights/diagnosticSettings` 2021-05-01-preview (the newest version
with `categoryGroup`, also used by the other compositions). No external
modules, restore or provider download.

The integration test relocates the exact source closure, then runs Bicep
format, lint, `build`, and `build-params` for the dev and prod examples. It
evaluates every exported guard with Bicep's native parameter evaluator,
including the production rejections. Terraform runs `fmt -check` and runs
`validate -json` / `test -no-color` against the **unchanged variables.tf
alone** with the same positive and negative cases as Bicep.

Full resource validation and the mocked plans in `terraform/tests` need the
reviewed Azure/azapi 2.13.0 mirror that Container Apps uses. Set
`CONTAINER_APPS_AZAPI_MIRROR`; tests then run `terraform init -backend=false
-input=false -plugin-dir=<mirror>`. **No mirror means a reported skip, not a
provider-validation pass.** Mocks do not certify ARM behavior, quota, model
availability, policies or permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Deleted
deployments, projects and resources, data created through the project endpoint
(agents, threads, files, evaluations), private DNS records, removed grants and
lock removals cannot be undone by a source revert; a deleted resource can be
recovered only within 48 hours. Omitting the workspace input in dev/test makes
Terraform delete the diagnostic setting; a Bicep incremental deployment leaves
it in place, so delete it explicitly. Logs and metrics already ingested stay in
the workspace for its retention period. Never switch Bicep/Terraform ownership
by applying the other source; review import and state migration first.

## Sources

Checked in November 2026:

- [Role-based access control for Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-foundry),
  [authentication and authorization](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/authentication-authorization-foundry),
  [Foundry Models with Entra ID](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/how-to/configure-entra-id)
  and [AI + machine learning built-in roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/ai-machine-learning).
- [Foundry SDK and endpoints](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview),
  [create a Foundry resource with Bicep](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/create-resource-template)
  and the official [infrastructure samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep)
  (`00-basic`, `10-private-network-basic`).
- [Models sold directly by Azure](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/concepts/models-sold-directly-by-azure)
  and [model retirements](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-retirements).
- [Private endpoint DNS zones](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns),
  [supported logs for Cognitive Services accounts](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-logs/microsoft-cognitiveservices-accounts-logs)
  and [recover or purge deleted resources](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources).
- [Cognitive Services REST specification](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/cognitiveservices/resource-manager/Microsoft.CognitiveServices/CognitiveServices/stable)
  and [azurerm 5.13.0 resource docs](https://github.com/hashicorp/terraform-provider-azurerm/tree/v5.13.0/website/docs/r).
- OCR: [Document Intelligence v4.0 quickstart](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/quickstarts/get-started-sdks-rest-api?view=doc-intel-4.0.0),
  [azure-ai-documentintelligence README](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/documentintelligence/azure-ai-documentintelligence)
  and [Foundry Tools authentication](https://learn.microsoft.com/en-us/azure/ai-services/authentication).
