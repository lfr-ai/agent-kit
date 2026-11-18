# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-dev-search"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  principal_id = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan

  assert {
    condition     = azapi_resource.search.body.sku.name == "basic" && jsonencode(azapi_resource.search.body.properties) == jsonencode({ disableLocalAuth = true, publicNetworkAccess = "Disabled" })
    error_message = "Development is Basic, private by default and declares disabled API keys; replicas and semantic ranker stay at their defaults."
  }
  assert {
    condition     = azapi_resource.index_reader.body.properties.principalId == var.principal_id && endswith(azapi_resource.index_reader.body.properties.roleDefinitionId, "/1407120a-92aa-4202-b7e9-c0e197c71c8f")
    error_message = "Only the supplied identity receives Search Index Data Reader."
  }
  assert {
    condition     = length(azapi_resource.index_contributor) == 0 && length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.protection) == 0 && length(azapi_resource.diagnostics) == 0
    error_message = "Development without optional inputs must not create indexing, network, diagnostic or lock resources."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    name  = "sample-prod-search"
    # Synthetic object ID: not a real identity.
    indexing_principal_id = "11111111-1111-1111-1111-111111111111"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/search"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.search.windows.net"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.search.body.sku.name == "standard" && azapi_resource.search.body.properties.replicaCount == 2 && azapi_resource.search.body.properties.semanticSearch == "standard"
    error_message = "Production defaults to Standard with 2 replicas and the standard semantic ranker plan."
  }
  assert {
    condition     = azapi_resource.search.body.properties.publicNetworkAccess == "Disabled" && azapi_resource.search.body.properties.disableLocalAuth == true
    error_message = "Production must disable public network access and API keys."
  }
  assert {
    condition     = azapi_resource.index_contributor[0].body.properties.principalId == var.indexing_principal_id && endswith(azapi_resource.index_contributor[0].body.properties.roleDefinitionId, "/8ebe5a00-799e-43f5-93ac-243d3dce84a7")
    error_message = "The indexing identity receives Search Index Data Contributor."
  }
  assert {
    condition     = jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["searchService"]) && length(azapi_resource.dns_zone_group) == 1
    error_message = "Production must be reachable through the private endpoint and register private DNS."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties.logs) == jsonencode([{ category = "OperationLogs", enabled = true }])
    error_message = "Production must send OperationLogs to the workspace."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must lock the search service."
  }
}

run "reject_production_defaults" {
  command = plan
  variables {
    stage         = "prod"
    replica_count = 1
  }
  expect_failures = [var.replica_count, var.private_endpoint, var.log_analytics_workspace_id]
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
    name  = "sample-staging-search"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/search"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.search.windows.net"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.search.body.sku.name == "basic" && jsonencode(azapi_resource.search.body.properties) == jsonencode({ disableLocalAuth = true, publicNetworkAccess = "Disabled" })
    error_message = "Staging keeps Basic capacity but is private."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 1 && length(azapi_resource.diagnostics) == 1 && length(azapi_resource.protection) == 0
    error_message = "Staging needs the private endpoint and diagnostics but no production lock."
  }
}

run "development_allow_list" {
  command = plan
  variables {
    allow_public_network_access = true
    allowed_ip_ranges           = ["203.0.113.0/24"]
  }
  assert {
    condition     = jsonencode(azapi_resource.search.body.properties) == jsonencode({ disableLocalAuth = true, networkRuleSet = { ipRules = [{ value = "203.0.113.0/24" }] } })
    error_message = "The public opt-in must allow only the listed ranges."
  }
}

run "reject_wrong_dns_zone" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/search"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    }
  }
  expect_failures = [var.private_endpoint]
}
