# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {
  # Synthetic tenant: the embedded schema requires a GUID-length tenantId.
  mock_data "azapi_client_config" {
    defaults = { tenant_id = "00000000-0000-0000-0000-000000000000" }
  }
}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-dev-pg"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  administrator = {
    object_id = "00000000-0000-0000-0000-000000000000"
    name      = "sample-db-admins"
    type      = "Group"
  }
  database_name = "app"
}

run "development" {
  command = plan

  assert {
    condition     = jsonencode(keys(azapi_resource.server.body.properties)) == jsonencode(["authConfig", "network", "storage", "version"])
    error_message = "Development declares only version, Entra-only authentication, storage and network access."
  }
  assert {
    condition     = azapi_resource.server.body.properties.storage.storageSizeGB == 32 && azapi_resource.server.body.properties.storage.autoGrow == "Enabled"
    error_message = "Storage defaults to the smallest Premium SSD size, 32 GiB, with autogrow."
  }
  assert {
    condition     = azapi_resource.server.body.properties.network.publicNetworkAccess == "Disabled" && length(azapi_resource.firewall_rule) == 0
    error_message = "Development disables public network access by default."
  }
  assert {
    condition     = azapi_resource.server.body.properties.authConfig.passwordAuth == "Disabled" && azapi_resource.server.body.properties.authConfig.activeDirectoryAuth == "Enabled"
    error_message = "Password authentication must be disabled and Entra ID authentication enabled."
  }
  assert {
    condition     = azapi_resource.server.body.sku.tier == "Burstable" && azapi_resource.server.body.sku.name == "Standard_B1ms"
    error_message = "Development defaults to the smallest Burstable size."
  }
  assert {
    condition     = azapi_resource.administrator.name == var.administrator.object_id && azapi_resource.administrator.body.properties.principalType == "Group"
    error_message = "The supplied principal must become the Entra administrator."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.protection) == 0 && length(azapi_resource.diagnostics) == 0 && length(azapi_update_resource.extensions) == 0
    error_message = "Development without optional inputs must not create network, diagnostic, lock or extension resources."
  }
}

run "extensions" {
  command = plan
  variables {
    extensions = ["vector", "age"]
  }
  assert {
    condition     = azapi_update_resource.extensions[0].name == "azure.extensions" && azapi_update_resource.extensions[0].body.properties.value == "vector,age"
    error_message = "Requested extensions must be allowlisted as one comma-separated azure.extensions value."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    name  = "sample-prod-pg"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/postgresql"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.server.body.sku.tier == "GeneralPurpose" && azapi_resource.server.body.properties.highAvailability.mode == "ZoneRedundant" && azapi_resource.server.body.properties.backup.geoRedundantBackup == "Enabled"
    error_message = "Production defaults to General Purpose with zone-redundant HA and geo-redundant backup."
  }
  assert {
    condition     = azapi_resource.server.body.properties.network.publicNetworkAccess == "Disabled"
    error_message = "Production must disable public network access."
  }
  assert {
    condition     = jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["postgresqlServer"]) && length(azapi_resource.dns_zone_group) == 1
    error_message = "Production must be reachable through the private endpoint and register private DNS."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties.logs) == jsonencode([{ category = "PostgreSQLLogs", enabled = true }])
    error_message = "Production must send PostgreSQLLogs to the workspace."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must lock the server."
  }
}

run "reject_production_defaults" {
  command = plan
  variables {
    stage = "prod"
    sku   = { name = "Standard_B2s", tier = "Burstable" }
  }
  expect_failures = [var.sku, var.private_endpoint, var.log_analytics_workspace_id]
}

run "reject_staging_defaults" {
  command = plan
  variables {
    stage = "staging"
  }
  expect_failures = [var.private_endpoint, var.log_analytics_workspace_id]
}

run "staging" {
  command = plan
  variables {
    stage = "staging"
    name  = "sample-staging-pg"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/postgresql"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.server.body.properties.network.publicNetworkAccess == "Disabled" && length(azapi_resource.endpoint) == 1 && length(azapi_resource.diagnostics) == 1
    error_message = "Staging gets the production network and diagnostics guards."
  }
  assert {
    condition     = azapi_resource.server.body.sku.tier == "Burstable" && !contains(keys(azapi_resource.server.body.properties), "highAvailability") && length(azapi_resource.protection) == 0
    error_message = "Staging keeps the dev/test size, no HA and no lock: those are production cost choices."
  }
}

run "development_allow_list" {
  command = plan
  variables {
    allow_public_network_access = true
    allowed_ip_ranges           = ["203.0.113.0/24", "198.51.100.7"]
  }
  assert {
    condition     = azapi_resource.server.body.properties.network.publicNetworkAccess == "Enabled" && length(azapi_resource.firewall_rule) == 2
    error_message = "The explicit public opt-in adds one firewall rule per allowed range."
  }
  assert {
    condition     = azapi_resource.firewall_rule["203.0.113.0/24"].name == "allow-203-0-113-0-24" && jsonencode(azapi_resource.firewall_rule["203.0.113.0/24"].body.properties) == jsonencode({ endIpAddress = "203.0.113.255", startIpAddress = "203.0.113.0" })
    error_message = "A CIDR range becomes its first and last address."
  }
  assert {
    condition     = jsonencode(azapi_resource.firewall_rule["198.51.100.7"].body.properties) == jsonencode({ endIpAddress = "198.51.100.7", startIpAddress = "198.51.100.7" })
    error_message = "A single address becomes a one-address rule."
  }
}

run "larger_storage" {
  command = plan
  variables {
    storage_size_gb = 128
  }
  assert {
    condition     = azapi_resource.server.body.properties.storage.storageSizeGB == 128
    error_message = "A caller can start with more storage than the default."
  }
}

run "reject_storage_below_minimum" {
  command = plan
  variables {
    storage_size_gb = 16
  }
  expect_failures = [var.storage_size_gb]
}

run "reject_wrong_dns_zone" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/postgresql"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.database.windows.net"
    }
  }
  expect_failures = [var.private_endpoint]
}
