# Document Intelligence: operator gates, validation and sources

Start with the [consumer contract](README.md).

## Why a separate resource

The Foundry (`AIServices`) resource is not used for OCR:

- The Document Intelligence v4.0 (`2024-11-30`) quickstart says: "For Document
  Intelligence access only, create a Document Intelligence resource. You need a
  single-service resource if you intend to use Microsoft Entra authentication."
  The `azure-ai-documentintelligence` SDK README gives the same instruction.
- Least privilege: `Cognitive Services User` on a Foundry resource grants every
  data action on it, including all model inference; here it grants Document
  Intelligence only.
- Network isolation, lock, throughput limits and diagnostics stay per workload.
  The broader Foundry Tools authentication page describes Entra ID for
  multi-service resources in general; the service-specific guidance wins.

Content Understanding is Microsoft's newer generative option for document
extraction; it is out of scope here.

## Defaults this composition relies on

The sources declare only what differs from the platform default. They
deliberately **do not restate** these 2025-09-01 defaults: unrestricted
outbound access, dynamic throttling off, Microsoft-managed
encryption keys and no user-owned storage. `publicNetworkAccess` is always
declared: `Disabled` unless a dev or test caller without a private endpoint sets
`allowPublicNetworkAccess`, which also declares `networkAcls` with
`defaultAction: Deny` and the `allowedIpRanges` (an empty list denies all public
traffic). `disableLocalAuth: true` is declared because keys are enabled
by default, and `enabled: true` on each diagnostic-setting entry because the
API requires it. The resource has no managed identity because it calls no other
service.

Because these are not declared, a source deployment does not revert drift if
someone changes them later. Enforce the security settings with Azure Policy
(local authentication disabled, public network access disabled in staging and production).

## Operator gates and ownership

- The app identity already exists. Pass its **object (principal) ID**; the
  application authenticates with the identity's client ID. For the same,
  identically cased resource and principal IDs, Bicep `guid()` and Terraform
  `uuidv5()` produce the same assignment name; still let one tool own an
  environment. Allow a few minutes for a new grant to take effect.
- `Cognitive Services User` (`a97b65f3-24c7-4388-baec-2e87135dc908`) is the
  role Microsoft documents for Document Intelligence Entra ID calls. It also
  includes `listkeys`, which is harmless while local authentication stays
  disabled; keep that setting enforced by policy.
- The deploying identity needs role-assignment write access on the resource
  (for example a constrained Role Based Access Control Administrator
  assignment).
- Register `Microsoft.CognitiveServices` and confirm the region offers
  Document Intelligence `S0` and the v4.0 models you call. Request a higher
  analyze rate through support before production load exceeds 15 requests per
  second.
- `name` is also the immutable custom subdomain; changing it creates a new
  resource. Deleted resources stay soft-deleted for 48 hours and block the
  name until purged or recovered.
- For a private endpoint, provide an existing same-region subnet and an
  existing `privatelink.cognitiveservices.azure.com` zone with a VNet link.
  Clients keep using the public host name, which resolves to the private
  address. Documents passed by URL must then be reachable from the service;
  sending the bytes in the request avoids that dependency.
- The production lock covers the resource and its grant. Rotating
  `principalId` in production therefore needs a reviewed lock removal. A Bicep
  incremental deployment leaves the previous assignment in place: remove stale
  grants explicitly.
- The lock does **not** block updates or an actor who may remove locks.
  Terraform destroy removes its own lock first; operator approvals must deny
  unreviewed destroy, replacement and lock removal.
- Diagnostics need an existing Log Analytics workspace (required in
  production). Ingestion and retention are billed by the workspace. The
  deploying identity needs diagnostic-settings write access on the resource and
  access to the workspace. Delete the setting before deleting or re-creating
  the resource: Azure Monitor can reapply leftover settings to a resource with
  the same ID.
- The guards accept only Azure public-cloud private DNS zones, by exact ARM ID
  shape and casing, and a `Microsoft.Network/virtualNetworks/*/subnets/*`
  subnet ID.

## Offline checks and pins

Checked tool baseline: **Bicep 0.39.26** and **Terraform 1.11.3**. Terraform
pins **Azure/azapi 2.13.0**, like every other delivery composition; azurerm 5.x
`azurerm_cognitive_account` is the equivalent, and switching is a reviewed
change with state migration. API versions: `Microsoft.CognitiveServices`
2025-09-01, the newest GA version in the local Bicep type index,
`Microsoft.Network` 2025-01-01 (same reason), role assignments 2022-04-01,
locks 2020-05-01 and `Microsoft.Insights/diagnosticSettings`
2021-05-01-preview (the newest version with `categoryGroup`, also used by the
other compositions). The data-plane API `2024-11-30` is the current GA
Document Intelligence version. No external modules, restore or provider
download.

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
provider-validation pass.** Mocks do not certify ARM behavior, policies or
permissions.

## Rollback

Before deployment, remove this directory, its integration test, its catalog
entry and the delivery README row; no cloud state has changed. After adoption,
revert inputs through the owning IaC tool and review the plan. Deleted
resources, private DNS records, removed grants and lock removals cannot be
undone by a source revert; a deleted resource can be recovered only within 48
hours. Analyze results are kept by the service only temporarily, so the app
owns any copies. Omitting the workspace input in dev/test makes Terraform
delete the diagnostic setting; a Bicep incremental deployment leaves it in
place, so delete it explicitly. Logs and metrics already ingested stay in the
workspace for its retention period. Never switch Bicep/Terraform ownership by
applying the other source; review import and state migration first.

## Sources

Checked in November 2026:

- [Document Intelligence v4.0 quickstart](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/quickstarts/get-started-sdks-rest-api?view=doc-intel-4.0.0)
  and the [azure-ai-documentintelligence README](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/documentintelligence/azure-ai-documentintelligence)
  (single-service resource for Entra ID).
- [Read model](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0),
  [layout model](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)
  and [service limits](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0).
- [Foundry Tools authentication](https://learn.microsoft.com/en-us/azure/ai-services/authentication)
  and [AI + machine learning built-in roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/ai-machine-learning).
- [Private endpoint DNS zones](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns),
  [supported logs for Cognitive Services accounts](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-logs/microsoft-cognitiveservices-accounts-logs)
  and [recover or purge deleted resources](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources).
- [Cognitive Services REST specification](https://github.com/Azure/azure-rest-api-specs/tree/main/specification/cognitiveservices/resource-manager/Microsoft.CognitiveServices/CognitiveServices/stable)
  and [azurerm 5.13.0 resource docs](https://github.com/hashicorp/terraform-provider-azurerm/tree/v5.13.0/website/docs/r).
