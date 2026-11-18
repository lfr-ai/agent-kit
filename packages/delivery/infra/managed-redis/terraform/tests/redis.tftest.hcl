# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-dev"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  principal_id = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan

  assert {
    condition     = azapi_resource.cluster.body.sku.name == "Balanced_B0" && jsonencode(azapi_resource.cluster.body.properties) == jsonencode({ publicNetworkAccess = "Disabled" })
    error_message = "Development uses the small default SKU and disables public network access without an opt-in."
  }
  assert {
    condition     = jsonencode(azapi_resource.database.body.properties) == jsonencode({ clusteringPolicy = "EnterpriseCluster", accessKeysAuthentication = "Disabled" })
    error_message = "The database must disable access keys explicitly and declare nothing else."
  }
  assert {
    condition     = azapi_resource.access.body.properties.accessPolicyName == "default" && azapi_resource.access.body.properties.user.objectId == var.principal_id
    error_message = "Only the supplied identity receives the default data access policy."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.protection) == 0
    error_message = "Development must not create network or lock resources."
  }
  assert {
    condition     = length(azapi_resource.cluster_diagnostics) == 0 && length(azapi_resource.database_diagnostics) == 0
    error_message = "Development without a workspace must not create diagnostic settings."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    sku   = "Balanced_B3"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/redis"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.redis.azure.net"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.cluster.body.properties.publicNetworkAccess == "Disabled" && jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["redisEnterprise"])
    error_message = "Production must be reachable only through the private endpoint."
  }
  assert {
    condition     = length(azapi_resource.dns_zone_group) == 1 && length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must register private DNS and lock the cache."
  }
  assert {
    condition     = azapi_resource.database.body.properties.accessKeysAuthentication == "Disabled"
    error_message = "Production must keep access keys disabled; Entra ID is the only data-plane credential."
  }
  assert {
    condition     = jsonencode(azapi_resource.cluster_diagnostics[0].body.properties.metrics) == jsonencode([{ category = "AllMetrics", enabled = true }]) && !can(azapi_resource.cluster_diagnostics[0].body.properties.logs)
    error_message = "Production must export cluster metrics to the workspace."
  }
  assert {
    condition     = jsonencode(azapi_resource.database_diagnostics[0].body.properties.logs) == jsonencode([{ category = "ConnectionEvents", enabled = true }]) && azapi_resource.database_diagnostics[0].body.properties.workspaceId == var.log_analytics_workspace_id
    error_message = "Production must export database connection logs to the workspace."
  }
}

run "development_public_opt_in" {
  command = plan
  variables {
    allow_public_network_access = true
  }
  assert {
    condition     = azapi_resource.cluster.body.properties.publicNetworkAccess == "Enabled"
    error_message = "The explicit dev or test opt-in keeps the public endpoint."
  }
}

run "reject_production_defaults" {
  command = plan
  variables {
    stage = "prod"
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

run "reject_malformed_workspace" {
  command = plan
  variables {
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring"
  }
  expect_failures = [var.log_analytics_workspace_id]
}
