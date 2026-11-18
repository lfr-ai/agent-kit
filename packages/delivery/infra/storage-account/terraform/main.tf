locals {
  tags                  = { stage = var.stage }
  blob_contributor_role = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
  # Production recovery window for deleted blobs and containers.
  soft_delete_retention_days = 30
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
  # Like Bicep subscriptionResourceId(): the resource group's subscription, not the provider's.
  subscription_scope = "/subscriptions/${split("/", var.resource_group_id)[2]}"
}

# Only non-defaults are declared, plus anonymous access pinned off. HTTPS only, the Hot
# tier and no cross-tenant replication are defaults. Shared keys are allowed and an unset
# minimum TLS version accepts TLS 1.0 by default, so both are declared. Public network
# access is disabled unless a dev or test caller opts in to an IP allow list.
resource "azapi_resource" "account" {
  type      = "Microsoft.Storage/storageAccounts@2025-06-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    kind = "StorageV2"
    sku  = { name = var.stage == "prod" ? "Standard_ZRS" : "Standard_LRS" }
    properties = merge(
      {
        allowSharedKeyAccess         = false
        defaultToOAuthAuthentication = true
        allowBlobPublicAccess        = false
        minimumTlsVersion            = "TLS1_2"
      },
      var.allow_public_network_access ? {} : { publicNetworkAccess = "Disabled" },
      var.allow_public_network_access ? {
        networkAcls = {
          defaultAction = "Deny"
          ipRules       = [for value in var.allowed_ip_ranges : { value = value, action = "Allow" }]
        }
      } : {}
    )
  }
  response_export_values = ["properties.primaryEndpoints.blob"]
}

# Production keeps every overwrite as a version; deleted blobs and containers stay
# recoverable for soft_delete_retention_days. Dev/test keep the platform defaults (all off).
resource "azapi_resource" "blob_service" {
  type      = "Microsoft.Storage/storageAccounts/blobServices@2025-06-01"
  name      = "default"
  parent_id = azapi_resource.account.id
  body = {
    # Separate scalar and object maps so each conditional has compatible types.
    properties = merge(
      var.stage == "prod" ? { isVersioningEnabled = true } : {},
      var.stage == "prod" ? {
        deleteRetentionPolicy          = { enabled = true, days = local.soft_delete_retention_days }
        containerDeleteRetentionPolicy = { enabled = true, days = local.soft_delete_retention_days }
      } : {}
    )
  }
  response_export_values = []
}

resource "azapi_resource" "container" {
  for_each               = toset(var.containers)
  type                   = "Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01"
  name                   = each.value
  parent_id              = azapi_resource.blob_service.id
  response_export_values = []
}

# Narrowest owned scope: each managed container, or the account when none is managed.
resource "azapi_resource" "container_blob_contributor" {
  for_each  = azapi_resource.container
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${each.value.id}-${var.principal_id}-${local.blob_contributor_role}")
  parent_id = each.value.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.blob_contributor_role}"
      principalId      = var.principal_id
      principalType    = "ServicePrincipal"
    }
  }
  response_export_values = []
}

resource "azapi_resource" "account_blob_contributor" {
  count     = length(var.containers) == 0 ? 1 : 0
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.account.id}-${var.principal_id}-${local.blob_contributor_role}")
  parent_id = azapi_resource.account.id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.blob_contributor_role}"
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
          groupIds             = ["blob"]
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
        name       = "blob"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

# Blob logs exist only on the blob service, not on the account.
resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "blob-diagnostics"
  parent_id = azapi_resource.blob_service.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs = [
        { category = "StorageRead", enabled = true },
        { category = "StorageWrite", enabled = true },
        { category = "StorageDelete", enabled = true },
      ]
      metrics = [{ category = "Transaction", enabled = true }]
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

  # Create the inherited lock last; reverse destroy must unlock before children.
  depends_on = [
    azapi_resource.blob_service,
    azapi_resource.container,
    azapi_resource.container_blob_contributor,
    azapi_resource.account_blob_contributor,
    azapi_resource.diagnostics,
  ]
}
