locals {
  tags             = { stage = var.stage }
  role_definitions = "/subscriptions/${split("/", var.resource_group_id)[2]}/providers/Microsoft.Authorization/roleDefinitions"
  # Built-in Cognitive Services User; on this single-service resource it grants Document Intelligence only.
  cognitive_services_user = "a97b65f3-24c7-4388-baec-2e87135dc908"
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
}

# Public access is disabled unless a dev or test caller opts in to a deny-by-default
# network ACL with an IP allow list.
resource "azapi_resource" "account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-09-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    kind = "FormRecognizer"
    sku  = { name = "S0" }
    properties = merge(
      {
        customSubDomainName = var.name
        disableLocalAuth    = true
        publicNetworkAccess = var.allow_public_network_access ? "Enabled" : "Disabled"
      },
      var.allow_public_network_access ? {
        networkAcls = {
          defaultAction = "Deny"
          ipRules       = [for value in var.allowed_ip_ranges : { value = value }]
        }
      } : {}
    )
  }
  # Never export the full response or call listKeys.
  response_export_values = ["properties.endpoint"]
}

resource "azapi_resource" "analyze_access" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.account.id}-${var.principal_id}-${local.cognitive_services_user}")
  parent_id = azapi_resource.account.id
  body = {
    properties = {
      roleDefinitionId = "${local.role_definitions}/${local.cognitive_services_user}"
      principalId      = var.principal_id
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
          privateLinkServiceId = azapi_resource.account.id
          groupIds             = ["account"]
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
        name       = "cognitiveservices"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "document-intelligence-logs"
  parent_id = azapi_resource.account.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs        = [{ categoryGroup = "allLogs", enabled = true }]
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
  parent_id              = azapi_resource.account.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
