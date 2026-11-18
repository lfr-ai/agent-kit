# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-dev-cosmos"
  stage             = "dev"
}

run "development" {
  command = plan

  assert {
    condition     = jsonencode(azapi_resource.account.body.properties) == jsonencode({ capabilities = [{ name = "EnableServerless" }], databaseAccountOfferType = "Standard", disableLocalAuth = true, locations = [{ failoverPriority = 0, locationName = "westeurope" }], minimalTlsVersion = "Tls12", publicNetworkAccess = "Disabled" })
    error_message = "Development is a serverless, single-region NoSQL account with local authentication and public network access disabled."
  }
  assert {
    condition     = length(azapi_resource.database) == 0 && length(azapi_resource.container) == 0 && length(azapi_resource.data_contributor) == 0
    error_message = "Without inputs no database, container or data-plane role assignment is created."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.diagnostics) == 0 && length(azapi_resource.protection) == 0
    error_message = "Development without optional inputs must not create network, diagnostic or lock resources."
  }
  assert {
    condition     = output.database_name == null && length(output.container_names) == 0
    error_message = "Without a database the name is null and the container list is empty."
  }
}

run "serverless_database" {
  command = plan
  variables {
    database = { name = "app", containers = [{ name = "items", partition_key_path = "/tenantId" }] }
  }
  assert {
    condition     = jsonencode(azapi_resource.database[0].body.properties) == jsonencode({ resource = { id = "app" } })
    error_message = "Serverless databases declare no throughput."
  }
  assert {
    condition     = jsonencode(azapi_resource.container["items"].body.properties.resource) == jsonencode({ id = "items", partitionKey = { paths = ["/tenantId"], version = 2 } })
    error_message = "Containers use the supplied partition key path with large partition keys."
  }
  assert {
    condition     = output.database_name == "app" && jsonencode(output.container_names) == jsonencode(["items"])
    error_message = "Outputs name the created database and containers."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    name  = "sample-prod-cosmos"
    database = {
      name = "app"
      containers = [
        { name = "items", partition_key_path = "/tenantId" },
        { name = "events", partition_key_path = "/streamId" },
      ]
    }
    autoscale_max_throughput = 4000
    principal_id             = "00000000-0000-0000-0000-000000000000"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/cosmos-db"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.documents.azure.com"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  # A realistic ARM ID makes the role-assignment name checkable against Bicep guid().
  override_resource {
    target          = azapi_resource.account
    override_during = plan
    values = {
      id     = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.DocumentDB/databaseAccounts/sample-prod-cosmos"
      output = { properties = { documentEndpoint = "https://sample-prod-cosmos.documents.azure.com:443/" } }
    }
  }
  assert {
    condition     = output.document_endpoint == "https://sample-prod-cosmos.documents.azure.com:443/" && output.database_name == "app" && jsonencode(output.container_names) == jsonencode(["events", "items"])
    error_message = "Outputs expose the endpoint, database and sorted container names, never keys."
  }
  assert {
    condition     = jsonencode(azapi_resource.account.body.properties) == jsonencode({ backupPolicy = { continuousModeProperties = { tier = "Continuous30Days" }, type = "Continuous" }, databaseAccountOfferType = "Standard", disableLocalAuth = true, locations = [{ failoverPriority = 0, isZoneRedundant = true, locationName = "westeurope" }], minimalTlsVersion = "Tls12", publicNetworkAccess = "Disabled" })
    error_message = "Production is provisioned, zone redundant, continuously backed up, private and Entra-only."
  }
  assert {
    condition     = azapi_resource.database[0].body.properties.options.autoscaleSettings.maxThroughput == 4000 && jsonencode(sort(keys(azapi_resource.container))) == jsonencode(["events", "items"])
    error_message = "Production shares autoscale throughput across the requested containers."
  }
  assert {
    condition     = azapi_resource.data_contributor[0].name == "997663ff-3563-57d3-9431-a28169046b6d" && jsonencode(azapi_resource.data_contributor[0].body.properties) == jsonencode({ principalId = var.principal_id, roleDefinitionId = "${azapi_resource.account.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002", scope = azapi_resource.account.id })
    error_message = "The principal gets Cosmos DB Built-in Data Contributor on the account, named like Bicep guid()."
  }
  assert {
    condition     = jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["Sql"]) && azapi_resource.dns_zone_group[0].body.properties.privateDnsZoneConfigs[0].properties.privateDnsZoneId == var.private_endpoint.private_dns_zone_id
    error_message = "Production must be reachable through the Sql private endpoint and register private DNS."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties) == jsonencode({ logAnalyticsDestinationType = "Dedicated", logs = [{ category = "DataPlaneRequests", enabled = true }, { category = "ControlPlaneRequests", enabled = true }], metrics = [{ category = "Requests", enabled = true }], workspaceId = var.log_analytics_workspace_id })
    error_message = "Production sends request logs and metrics to resource-specific workspace tables."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must lock the account."
  }
}

run "private_test" {
  command = plan
  variables {
    stage = "test"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/cosmos-db"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.documents.azure.com"
    }
  }
  assert {
    condition     = azapi_resource.account.body.properties.publicNetworkAccess == "Disabled" && length(azapi_resource.endpoint) == 1 && length(azapi_resource.protection) == 0
    error_message = "Optional private networking does not turn test into production."
  }
}

run "reject_production_defaults" {
  command = plan
  variables {
    stage = "prod"
  }
  expect_failures = [var.private_endpoint, var.log_analytics_workspace_id]
}

run "reject_staging_defaults" {
  command = plan
  variables {
    stage = "staging"
  }
  expect_failures = [var.private_endpoint, var.log_analytics_workspace_id]
}

run "development_allow_list" {
  command = plan
  variables {
    allow_public_network_access = true
    allowed_ip_ranges           = ["203.0.113.0/24"]
  }
  assert {
    condition     = !contains(keys(azapi_resource.account.body.properties), "publicNetworkAccess") && jsonencode(azapi_resource.account.body.properties.ipRules) == jsonencode([{ ipAddressOrRange = "203.0.113.0/24" }])
    error_message = "The public opt-in must allow only the listed ranges."
  }
}

run "reject_wrong_dns_zone" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/cosmos-db"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.mongo.cosmos.azure.com"
    }
  }
  expect_failures = [var.private_endpoint]
}
