locals {
  tags = { stage = var.stage }
}

# Only non-defaults are declared: Entra ID auth, TLS 1.2, encrypted client protocol,
# port 10000 and high availability are platform defaults. Access keys are disabled
# explicitly on the database, so Entra ID is the only data-plane credential.
resource "azapi_resource" "cluster" {
  type      = "Microsoft.Cache/redisEnterprise@2025-07-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    sku = { name = var.sku }
    properties = {
      # Required by this API version; public only on an explicit dev or test opt-in.
      publicNetworkAccess = var.allow_public_network_access ? "Enabled" : "Disabled"
    }
  }
  # Never export the full response or call listKeys.
  response_export_values = ["properties.hostName"]
}

# EnterpriseCluster exposes one endpoint for non-cluster-aware clients (redis-py Redis).
resource "azapi_resource" "database" {
  type      = "Microsoft.Cache/redisEnterprise/databases@2025-07-01"
  name      = "default"
  parent_id = azapi_resource.cluster.id
  body = {
    properties = {
      clusteringPolicy         = "EnterpriseCluster"
      accessKeysAuthentication = "Disabled"
    }
  }
  response_export_values = ["properties.port"]
}

resource "azapi_resource" "access" {
  type      = "Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments@2025-07-01"
  name      = replace(var.principal_id, "-", "")
  parent_id = azapi_resource.database.id
  body = {
    properties = {
      accessPolicyName = "default"
      user             = { objectId = var.principal_id }
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
          privateLinkServiceId = azapi_resource.cluster.id
          groupIds             = ["redisEnterprise"]
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
        name       = "redis"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

# Platform metrics are exported by the cluster; resource logs by the database.
resource "azapi_resource" "cluster_diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "redis-metrics"
  parent_id = azapi_resource.cluster.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      metrics     = [{ category = "AllMetrics", enabled = true }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "database_diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "redis-connection-logs"
  parent_id = azapi_resource.database.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs        = [{ category = "ConnectionEvents", enabled = true }]
    }
  }
  response_export_values = []
}

# Resource-scoped: never protects unrelated resources in the caller's group.
resource "azapi_resource" "protection" {
  count                  = var.stage == "prod" ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.cluster.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
