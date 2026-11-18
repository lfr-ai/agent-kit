locals {
  # Monitoring Metrics Publisher: the built-in role for Entra ID authenticated ingestion.
  publisher_role_id = "3913510d-42f4-4e42-8a64-420c390055eb"
  subscription_id   = regex("^/subscriptions/[^/]+", var.resource_group_id)
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
}

# Only non-defaults are declared: public ingestion and query, sampling, IP
# masking and retention (owned by the workspace) stay at platform defaults.
resource "azapi_resource" "component" {
  type      = "Microsoft.Insights/components@2020-02-02"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = { stage = var.stage }
  body = {
    # Required by this API version.
    kind = "web"
    properties = {
      # Required by this API version.
      Application_Type    = "web"
      WorkspaceResourceId = var.log_analytics_workspace_id
      # dev keeps instrumentation-key ingestion for local runs; test, staging and prod accept Entra ID only.
      DisableLocalAuth = var.stage != "dev"
    }
  }
  # Never export the full response.
  response_export_values = ["properties.ConnectionString"]
}

resource "azapi_resource" "publisher" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.component.id}-${var.principal_id}-${local.publisher_role_id}")
  parent_id = azapi_resource.component.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.publisher_role_id}"
      principalId      = var.principal_id
      # Lets ARM assign a newly created managed identity before Entra ID replication completes.
      principalType = "ServicePrincipal"
    }
  }
  response_export_values = []
}
