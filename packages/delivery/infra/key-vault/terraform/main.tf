locals {
  tags              = { stage = var.stage }
  secrets_user_role = "4633458b-17de-408a-b874-0445c86b69e6"
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
  # Like Bicep subscriptionResourceId(): the resource group's subscription, not the provider's.
  subscription_scope = "/subscriptions/${split("/", var.resource_group_id)[2]}"
}

data "azapi_client_config" "current" {}

# RBAC authorization and soft delete (90 days) are the 2026-02-01 defaults; they are
# declared anyway so a redeployment reverts drift to access policies. Purge protection
# cannot be turned off again, so it is set in staging and production only. Public network
# access is disabled unless a dev or test caller opts in to an IP allow list.
resource "azapi_resource" "vault" {
  type      = "Microsoft.KeyVault/vaults@2026-02-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    properties = merge(
      {
        tenantId                = data.azapi_client_config.current.tenant_id
        sku                     = { family = "A", name = "standard" }
        enableRbacAuthorization = true
        enableSoftDelete        = true
      },
      contains(["staging", "prod"], var.stage) ? { enablePurgeProtection = true } : {},
      var.allow_public_network_access ? {} : { publicNetworkAccess = "Disabled" },
      var.allow_public_network_access ? {
        networkAcls = {
          defaultAction = "Deny"
          ipRules       = [for value in var.allowed_ip_ranges : { value = value }]
        }
      } : {}
    )
  }
  response_export_values = ["properties.vaultUri"]
}

resource "azapi_resource" "secrets_user" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.vault.id}-${var.principal_id}-${local.secrets_user_role}")
  parent_id = azapi_resource.vault.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.secrets_user_role}"
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
          privateLinkServiceId = azapi_resource.vault.id
          groupIds             = ["vault"]
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
        name       = "vault"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "key-vault-audit"
  parent_id = azapi_resource.vault.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs        = [{ category = "AuditEvent", enabled = true }]
    }
  }
  response_export_values = []
}

# Resource-scoped: never protects unrelated resources in the caller's group.
resource "azapi_resource" "protection" {
  count                  = var.stage == "prod" ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.vault.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
