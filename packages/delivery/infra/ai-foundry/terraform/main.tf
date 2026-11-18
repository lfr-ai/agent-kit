locals {
  tags = { stage = var.stage }
  # Built-in role definition names are the same in every tenant.
  role_definitions = "/subscriptions/${split("/", var.resource_group_id)[2]}/providers/Microsoft.Authorization/roleDefinitions"
  openai_user      = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
  foundry_user     = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
}

# Public access is disabled unless a dev or test caller opts in to a deny-by-default
# network ACL with an IP allow list.
resource "azapi_resource" "foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-09-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  identity {
    type = "SystemAssigned"
  }
  body = {
    kind = "AIServices"
    sku  = { name = "S0" }
    properties = merge(
      {
        allowProjectManagement = true
        customSubDomainName    = var.name
        disableLocalAuth       = true
        publicNetworkAccess    = var.allow_public_network_access ? "Enabled" : "Disabled"
      },
      var.allow_public_network_access ? {
        networkAcls = {
          defaultAction = var.allow_all_public_clients ? "Allow" : "Deny"
          ipRules       = [for value in var.allowed_ip_ranges : { value = value }]
        }
      } : {}
    )
  }
  # Never export the full response or call listKeys.
  response_export_values = []
}

resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-09-01"
  name      = var.name
  parent_id = azapi_resource.foundry.id
  location  = var.location
  tags      = local.tags
  identity {
    type = "SystemAssigned"
  }
  body                   = { properties = {} }
  response_export_values = []
}

resource "azapi_resource" "model_deployment" {
  for_each  = { for deployment in var.deployments : deployment.name => deployment }
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-09-01"
  name      = each.key
  parent_id = azapi_resource.foundry.id
  body = {
    sku = { name = each.value.sku, capacity = each.value.capacity }
    properties = {
      model = { format = each.value.format, name = each.value.model, version = each.value.version }
    }
  }
  # The account accepts one child operation at a time, so deployments run serially.
  locks                  = [azapi_resource.foundry.id]
  depends_on             = [azapi_resource.project]
  response_export_values = []
}

# OpenAI-compatible inference on the account; no key listing or management rights.
resource "azapi_resource" "inference_access" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.foundry.id}-${var.principal_id}-${local.openai_user}")
  parent_id = azapi_resource.foundry.id
  body = {
    properties = {
      roleDefinitionId = "${local.role_definitions}/${local.openai_user}"
      principalId      = var.principal_id
      principalType    = "ServicePrincipal"
    }
  }
  response_export_values = []
}

# Microsoft's recommended role for the project endpoint (Foundry SDK, agents, responses).
resource "azapi_resource" "project_access" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.project.id}-${var.principal_id}-${local.foundry_user}")
  parent_id = azapi_resource.project.id
  body = {
    properties = {
      roleDefinitionId = "${local.role_definitions}/${local.foundry_user}"
      principalId      = var.principal_id
      principalType    = "ServicePrincipal"
    }
  }
  response_export_values = []
}

# Binding before the account finishes provisioning fails with AccountProvisioningStateInvalid.
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
          privateLinkServiceId = azapi_resource.foundry.id
          groupIds             = ["account"]
        }
      }]
    }
  }
  depends_on             = [azapi_resource.project, azapi_resource.model_deployment]
  response_export_values = []
}

resource "azapi_resource" "dns_zone_group" {
  count     = length(azapi_resource.endpoint)
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01"
  name      = "default"
  parent_id = azapi_resource.endpoint[0].id
  body = {
    properties = {
      privateDnsZoneConfigs = [for id in var.private_endpoint.private_dns_zone_ids : {
        name       = reverse(split("/", id))[0]
        properties = { privateDnsZoneId = id }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "foundry-logs"
  parent_id = azapi_resource.foundry.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs        = [{ categoryGroup = "allLogs", enabled = true }]
      metrics     = [{ category = "AllMetrics", enabled = true }]
    }
  }
  response_export_values = []
}

# Resource-scoped: inherited by the project and deployments, never by unrelated resources.
resource "azapi_resource" "protection" {
  count                  = var.stage == "prod" ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.foundry.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
