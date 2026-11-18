locals {
  tags             = { stage = var.stage }
  replica_count    = var.replica_count != null ? var.replica_count : (var.stage == "prod" ? local.production_min_replicas : null)
  reader_role      = "1407120a-92aa-4202-b7e9-c0e197c71c8f" # Search Index Data Reader
  contributor_role = "8ebe5a00-799e-43f5-93ac-243d3dce84a7" # Search Index Data Contributor
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
  # Like Bicep subscriptionResourceId(): the resource group's subscription, not the provider's.
  subscription_scope = "/subscriptions/${split("/", var.resource_group_id)[2]}"
}

# Only non-defaults are declared: API keys are allowed by default, so they are disabled.
# Semantic ranker starts on the free plan; production opts in to the billed standard
# plan so queries keep working after the monthly free allowance. Two or more replicas
# spread across availability zones where the region has them. Public access is
# disabled unless a dev or test caller opts in to an IP allow list.
resource "azapi_resource" "search" {
  type      = "Microsoft.Search/searchServices@2025-05-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    sku = { name = var.stage == "prod" ? "standard" : "basic" }
    properties = merge(
      { disableLocalAuth = true },
      local.replica_count == null ? {} : { replicaCount = local.replica_count },
      var.stage == "prod" ? { semanticSearch = "standard" } : {},
      var.allow_public_network_access ? {} : { publicNetworkAccess = "Disabled" },
      var.allow_public_network_access ? { networkRuleSet = { ipRules = [for value in var.allowed_ip_ranges : { value = value }] } } : {}
    )
  }
  response_export_values = ["properties.endpoint"]
}

resource "azapi_resource" "index_reader" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.search.id}-${var.principal_id}-${local.reader_role}")
  parent_id = azapi_resource.search.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.reader_role}"
      principalId      = var.principal_id
      principalType    = "ServicePrincipal"
    }
  }
  response_export_values = []
}

resource "azapi_resource" "index_contributor" {
  count     = var.indexing_principal_id == null ? 0 : 1
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.search.id}-${var.indexing_principal_id}-${local.contributor_role}")
  parent_id = azapi_resource.search.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.contributor_role}"
      principalId      = var.indexing_principal_id
      principalType    = "ServicePrincipal"
    }
  }
  response_export_values = []
}

resource "azapi_resource" "endpoint" {
  count     = var.private_endpoint == null ? 0 : 1
  type      = "Microsoft.Network/privateEndpoints@2025-01-01"
  name      = "${var.name}-pe"
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    properties = {
      subnet = { id = var.private_endpoint.subnet_id }
      privateLinkServiceConnections = [{
        name = var.name
        properties = {
          privateLinkServiceId = azapi_resource.search.id
          groupIds             = ["searchService"]
        }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "dns_zone_group" {
  count     = length(azapi_resource.endpoint)
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01"
  name      = "default"
  parent_id = azapi_resource.endpoint[0].id
  body = {
    properties = {
      privateDnsZoneConfigs = [{
        name       = "search"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "search-diagnostics"
  parent_id = azapi_resource.search.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs        = [{ category = "OperationLogs", enabled = true }]
      metrics     = [{ category = "AllMetrics", enabled = true }]
    }
  }
  response_export_values = []
}

# Resource-scoped: never protects unrelated resources in the caller's group.
resource "azapi_resource" "protection" {
  count                  = var.stage == "prod" ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.search.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
