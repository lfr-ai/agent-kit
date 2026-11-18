locals {
  tags = { stage = var.stage }
  sku = var.sku != null ? var.sku : (
    var.stage == "prod"
    ? { name = "Standard_D2ds_v5", tier = "GeneralPurpose" }
    : { name = "Standard_B1ms", tier = "Burstable" }
  )
}

data "azapi_client_config" "current" {}

# Only non-defaults are declared. Password authentication is on by default, so it is
# switched off explicitly. Storage has no documented default size; autogrow avoids a
# read-only server when the disk fills. Geo-redundant backup can only be chosen at creation.
# Public access is disabled unless a dev or test caller opts in; with no firewall rule
# the public endpoint still denies every client.
resource "azapi_resource" "server" {
  type      = "Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    sku = local.sku
    properties = merge(
      {
        version = "18"
        authConfig = {
          activeDirectoryAuth = "Enabled"
          passwordAuth        = "Disabled"
          tenantId            = data.azapi_client_config.current.tenant_id
        }
        storage = { storageSizeGB = var.storage_size_gb, autoGrow = "Enabled" }
        network = { publicNetworkAccess = var.allow_public_network_access ? "Enabled" : "Disabled" }
      },
      var.stage == "prod" ? {
        highAvailability = { mode = "ZoneRedundant" }
        backup           = { geoRedundantBackup = "Enabled" }
      } : {}
    )
  }
  response_export_values = ["properties.fullyQualifiedDomainName"]
}

resource "azapi_resource" "administrator" {
  type      = "Microsoft.DBforPostgreSQL/flexibleServers/administrators@2025-08-01"
  name      = var.administrator.object_id
  parent_id = azapi_resource.server.id
  body = {
    properties = {
      principalName = var.administrator.name
      principalType = var.administrator.type
      tenantId      = data.azapi_client_config.current.tenant_id
    }
  }
  response_export_values = []
}

# Server operations run one after another: parallel changes to one server can conflict.
resource "azapi_resource" "database" {
  type                   = "Microsoft.DBforPostgreSQL/flexibleServers/databases@2025-08-01"
  name                   = var.database_name
  parent_id              = azapi_resource.server.id
  response_export_values = []
  depends_on             = [azapi_resource.administrator]
}

# A dynamic parameter: no restart. Each database still runs CREATE EXTENSION.
# Server parameters cannot be deleted, so destroy leaves the value, as in Bicep.
resource "azapi_update_resource" "extensions" {
  count     = length(var.extensions) == 0 ? 0 : 1
  type      = "Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01"
  name      = "azure.extensions"
  parent_id = azapi_resource.server.id
  body = {
    properties = { value = join(",", var.extensions), source = "user-override" }
  }
  response_export_values = []
  depends_on             = [azapi_resource.database]
}

# Only with the explicit dev/test opt-in; the lock serializes rules like other server operations.
resource "azapi_resource" "firewall_rule" {
  for_each  = toset(var.allowed_ip_ranges)
  type      = "Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2025-08-01"
  name      = "allow-${replace(replace(each.value, ".", "-"), "/", "-")}"
  parent_id = azapi_resource.server.id
  body = {
    properties = {
      startIpAddress = cidrhost(strcontains(each.value, "/") ? each.value : "${each.value}/32", 0)
      endIpAddress   = cidrhost(strcontains(each.value, "/") ? each.value : "${each.value}/32", -1)
    }
  }
  locks                  = [azapi_resource.server.id]
  response_export_values = []
  depends_on             = [azapi_update_resource.extensions]
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
          privateLinkServiceId = azapi_resource.server.id
          groupIds             = ["postgresqlServer"]
        }
      }]
    }
  }
  response_export_values = []
  depends_on             = [azapi_resource.database, azapi_update_resource.extensions]
}

resource "azapi_resource" "dns_zone_group" {
  count     = length(azapi_resource.endpoint)
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01"
  name      = "default"
  parent_id = azapi_resource.endpoint[0].id
  body = {
    properties = {
      privateDnsZoneConfigs = [{
        name       = "postgresql"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "postgresql-diagnostics"
  parent_id = azapi_resource.server.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs        = [{ category = "PostgreSQLLogs", enabled = true }]
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
  parent_id              = azapi_resource.server.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
