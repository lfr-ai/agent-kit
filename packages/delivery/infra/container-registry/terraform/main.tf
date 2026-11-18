locals {
  tags     = { stage = var.stage }
  acr_pull = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
  acr_push = "8311e382-0749-4cb8-b61a-304f252e45ec"
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
  # Like Bicep subscriptionResourceId(): the resource group's subscription, not the provider's.
  subscription_scope = "/subscriptions/${split("/", var.resource_group_id)[2]}"
}

# The admin user and anonymous pull are disabled explicitly: Entra ID roles are the only
# registry credential. Otherwise only non-defaults are declared: zone redundancy where the
# region offers it, trusted-service bypass and AcrPull/AcrPush role mode are defaults.
# Production deletes untagged manifests after the default 7 days (Premium preview).
# Public access is disabled unless a dev or test caller opts in; Premium then denies
# all but the allow list.
resource "azapi_resource" "registry" {
  type      = "Microsoft.ContainerRegistry/registries@2025-11-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    sku = { name = var.sku }
    properties = merge(
      {
        adminUserEnabled     = false
        anonymousPullEnabled = false
      },
      var.allow_public_network_access ? {} : { publicNetworkAccess = "Disabled" },
      var.allow_public_network_access && var.sku == "Premium" ? {
        networkRuleSet = {
          defaultAction = "Deny"
          ipRules       = [for value in var.allowed_ip_ranges : { action = "Allow", value = value }]
        }
      } : {},
      var.stage == "prod" ? { policies = { retentionPolicy = { status = "enabled" } } } : {}
    )
  }
  response_export_values = ["properties.loginServer"]
}

resource "azapi_resource" "pull" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.registry.id}-${var.pull_principal_id}-${local.acr_pull}")
  parent_id = azapi_resource.registry.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.acr_pull}"
      principalId      = var.pull_principal_id
      principalType    = "ServicePrincipal"
    }
  }
  response_export_values = []
}

resource "azapi_resource" "push" {
  count     = var.push_principal_id == null ? 0 : 1
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.registry.id}-${var.push_principal_id}-${local.acr_push}")
  parent_id = azapi_resource.registry.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.acr_push}"
      principalId      = var.push_principal_id
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
          privateLinkServiceId = azapi_resource.registry.id
          groupIds             = ["registry"]
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
        name       = "registry"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "container-registry-audit"
  parent_id = azapi_resource.registry.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs = [
        { category = "ContainerRegistryLoginEvents", enabled = true },
        { category = "ContainerRegistryRepositoryEvents", enabled = true }
      ]
    }
  }
  response_export_values = []
}

# Resource-scoped: never protects unrelated resources in the caller's group.
resource "azapi_resource" "protection" {
  count                  = var.stage == "prod" ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.registry.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
