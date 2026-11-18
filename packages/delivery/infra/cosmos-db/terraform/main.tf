locals {
  tags       = { stage = var.stage }
  containers = var.database == null ? [] : var.database.containers
  # Cosmos DB Built-in Data Contributor, a data-plane role definition on every account.
  data_contributor_role = "00000000-0000-0000-0000-000000000002"
  # ARM guid() is UUIDv5 in this namespace, so the assignment name matches the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
}

# Only non-defaults are declared. The default kind, GlobalDocumentDB, is the NoSQL API.
# Local (key) authentication is disabled. The template reference documents TLS 1.0 as the
# unset minimum, so TLS 1.2 is declared. Dev/test/staging are serverless; production is
# provisioned, zone redundant and continuously backed up instead of the periodic default.
# Public network access is disabled unless a dev or test caller opts in to an IP allow list.
resource "azapi_resource" "account" {
  type      = "Microsoft.DocumentDB/databaseAccounts@2025-10-15"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    properties = merge(
      {
        databaseAccountOfferType = "Standard"
        locations = [merge(
          { locationName = var.location, failoverPriority = 0 },
          var.stage == "prod" ? { isZoneRedundant = true } : {}
        )]
        disableLocalAuth  = true
        minimalTlsVersion = "Tls12"
      },
      var.allow_public_network_access ? {} : { publicNetworkAccess = "Disabled" },
      var.allow_public_network_access ? {
        ipRules = [for value in var.allowed_ip_ranges : { ipAddressOrRange = value }]
      } : {},
      # Separate maps so each conditional has compatible types.
      var.stage == "prod" ? {
        backupPolicy = { type = "Continuous", continuousModeProperties = { tier = "Continuous30Days" } }
      } : {},
      var.stage == "prod" ? {} : { capabilities = [{ name = "EnableServerless" }] }
    )
  }
  response_export_values = ["properties.documentEndpoint"]
}

# Production shares autoscale throughput across the database's containers;
# serverless accounts reject any throughput option.
resource "azapi_resource" "database" {
  count     = var.database == null ? 0 : 1
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2025-10-15"
  name      = var.database.name
  parent_id = azapi_resource.account.id
  body = {
    properties = merge(
      { resource = { id = var.database.name } },
      var.stage == "prod" ? {
        options = { autoscaleSettings = { maxThroughput = var.autoscale_max_throughput } }
      } : {}
    )
  }
  response_export_values = []
}

# Version 2 (large) partition keys hash the whole key value; version 1 is the default.
resource "azapi_resource" "container" {
  for_each  = { for container in local.containers : container.name => container }
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15"
  name      = each.key
  parent_id = azapi_resource.database[0].id
  body = {
    properties = {
      resource = {
        id           = each.key
        partitionKey = { paths = [each.value.partition_key_path], version = 2 }
      }
    }
  }
  response_export_values = []
}

# A Cosmos DB data-plane role assignment, not an Azure RBAC role assignment.
resource "azapi_resource" "data_contributor" {
  count     = var.principal_id == null ? 0 : 1
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-10-15"
  name      = uuidv5(local.guid_namespace, "${azapi_resource.account.id}-${var.principal_id}-${local.data_contributor_role}")
  parent_id = azapi_resource.account.id
  body = {
    properties = {
      roleDefinitionId = "${azapi_resource.account.id}/sqlRoleDefinitions/${local.data_contributor_role}"
      principalId      = var.principal_id
      scope            = azapi_resource.account.id
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
          groupIds             = ["Sql"]
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
        name       = "cosmos-db"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

# Resource-specific tables are Microsoft's recommended destination for Cosmos DB logs.
resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "cosmos-db-diagnostics"
  parent_id = azapi_resource.account.id
  body = {
    properties = {
      workspaceId                 = var.log_analytics_workspace_id
      logAnalyticsDestinationType = "Dedicated"
      logs = [
        { category = "DataPlaneRequests", enabled = true },
        { category = "ControlPlaneRequests", enabled = true },
      ]
      metrics = [{ category = "Requests", enabled = true }]
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
    azapi_resource.database,
    azapi_resource.container,
    azapi_resource.data_contributor,
    azapi_resource.diagnostics,
  ]
}
