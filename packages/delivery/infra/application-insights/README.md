# Azure Application Insights (opt-in)

One workspace-based Application Insights resource on an **existing** Log
Analytics workspace, and the `Monitoring Metrics Publisher` grant that lets the
app's **existing** managed identity send telemetry with Entra ID. Choose
**one** canonical implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Reference `bicep/main.bicep` as a
resource-group-scoped module or `terraform` as a local Terraform child module.
The caller owns the resource group, workspace, identity, provider
authentication and state.

## What is included

| Part | Reason |
| --- | --- |
| Application Insights resource | Workspace-based: telemetry is stored, retained and billed in the workspace. Only non-default settings are declared. |
| `Monitoring Metrics Publisher` grant | Lets the app identity ingest with an Entra ID token, in every stage. |
| Input guards | Reject a workspace name instead of its ARM ID and a principal ID that is not GUID-shaped. They cannot tell an object ID from a client ID. |

## Inputs

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Required | Meaning |
| --- | --- |
| `location` | Azure region, normally the workspace region |
| `name` | Application Insights resource name; separate names/groups/state per stage |
| `stage` | `dev`, `test`, `staging`, `prod` |
| `logAnalyticsWorkspaceId` | ARM ID of the existing workspace (`/subscriptions/…/providers/Microsoft.OperationalInsights/workspaces/…`) |
| `principalId` | Object (principal) ID of the existing app identity, **not** its client ID |
| `resource_group_id` | Terraform only: existing resource group ARM ID |

There are no optional inputs.

| Stage | Ingestion authentication |
| --- | --- |
| `dev` | Entra ID **or** the connection string alone, so a developer can send telemetry from a laptop without an Azure role |
| `test`, `staging`, `prod` | **Entra ID only** (`DisableLocalAuth`); telemetry sent with only the connection string is rejected |

The deployed app authenticates with Entra ID in every stage, so its code path
does not change between stages; only the laptop shortcut is limited to `dev`.
Ingestion and query stay on the public endpoint with Entra ID; private
ingestion through an Azure Monitor Private Link Scope is a follow-up (see
[REFERENCE.md](REFERENCE.md#operator-gates-and-ownership)).

## Outputs

`applicationInsightsResourceId` and `connectionString`. Microsoft documents the
connection string's instrumentation key as a unique identifier, not a security
token or key, so it is a normal output and may be passed as a plain environment
variable (`APPLICATIONINSIGHTS_CONNECTION_STRING`). In test, staging and prod it is
not enough to send telemetry; the app also needs a token for the granted identity,
for example `ManagedIdentityCredential` with the identity's **client** ID.
Pass `connectionString` to the [container-apps](../container-apps/README.md)
`applicationInsightsConnectionString` input and supply the existing user-assigned
identity's resource ID as `existingIdentityResourceId`. With the connection
string set, the composition sets `APPLICATIONINSIGHTS_CONNECTION_STRING` and
derives `AZURE_CLIENT_ID` from that identity.

## Verify and adopt

From the repository root using installed tools:

```powershell
uv run --locked pytest tests\integration\delivery\infra\test_application_insights.py -q
```

The tests use the same Bicep 0.39.26 / Terraform 1.11.3 baseline and
**Azure/azapi 2.13.0** pin as Container Apps. Full Terraform validation reuses
the `CONTAINER_APPS_AZAPI_MIRROR` provider mirror. Missing tools or providers
are skips, not live validation.

Before adoption, rollback is removal of these sources and their test. After
adoption, telemetry already stored in the workspace is not undone by a source
revert. See [operator gates, rollback and sources](REFERENCE.md).
