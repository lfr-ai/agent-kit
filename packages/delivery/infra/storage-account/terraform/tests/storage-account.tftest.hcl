# Only mocked plans: never initialize an Azure account or apply resources.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sampledevstorage"
  stage             = "dev"
  principal_id      = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan

  # Realistic ARM IDs make role-assignment names checkable against Bicep guid().
  override_resource {
    target          = azapi_resource.account
    override_during = plan
    values = {
      id     = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Storage/storageAccounts/sampledevstorage"
      output = { properties = { primaryEndpoints = { blob = "https://sampledevstorage.blob.core.windows.net/" } } }
    }
  }

  assert {
    condition     = azapi_resource.account.body.kind == "StorageV2" && azapi_resource.account.body.sku.name == "Standard_LRS"
    error_message = "Development uses a general-purpose v2 LRS account."
  }
  assert {
    condition     = jsonencode(azapi_resource.account.body.properties) == jsonencode({ allowSharedKeyAccess = false, defaultToOAuthAuthentication = true, allowBlobPublicAccess = false, minimumTlsVersion = "TLS1_2", publicNetworkAccess = "Disabled" })
    error_message = "Storage is Entra-only with no anonymous blobs, minimum TLS 1.2 and no public network access by default."
  }
  assert {
    condition     = jsonencode(azapi_resource.blob_service.body.properties) == jsonencode({}) && length(azapi_resource.container) == 0
    error_message = "Development does not enable retention or create containers unless requested."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.diagnostics) == 0 && length(azapi_resource.protection) == 0
    error_message = "Development creates no optional network, diagnostics or lock resources."
  }
  assert {
    condition     = length(azapi_resource.container_blob_contributor) == 0 && length(azapi_resource.account_blob_contributor) == 1
    error_message = "Without managed containers, the runtime identity is granted at the account."
  }
  assert {
    condition     = azapi_resource.account_blob_contributor[0].parent_id == azapi_resource.account.id && azapi_resource.account_blob_contributor[0].name == "62eb3300-6905-5524-8277-5caf485a4f5d"
    error_message = "The account grant uses the Bicep guid(scope, principal, role) name."
  }
  assert {
    condition     = jsonencode(azapi_resource.account_blob_contributor[0].body.properties) == jsonencode({ roleDefinitionId = "/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe", principalId = var.principal_id, principalType = "ServicePrincipal" })
    error_message = "The runtime service principal gets Storage Blob Data Contributor."
  }
}

run "production" {
  command = plan
  variables {
    name       = "sampleprodstorage"
    stage      = "prod"
    containers = ["uploads", "exports"]
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/storage"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  override_resource {
    target          = azapi_resource.container["uploads"]
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Storage/storageAccounts/sampleprodstorage/blobServices/default/containers/uploads" }
  }
  override_resource {
    target          = azapi_resource.container["exports"]
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Storage/storageAccounts/sampleprodstorage/blobServices/default/containers/exports" }
  }
  assert {
    condition     = azapi_resource.account.body.sku.name == "Standard_ZRS" && jsonencode(azapi_resource.account.body.properties) == jsonencode({ allowSharedKeyAccess = false, defaultToOAuthAuthentication = true, allowBlobPublicAccess = false, minimumTlsVersion = "TLS1_2", publicNetworkAccess = "Disabled" })
    error_message = "Production is ZRS, private and Entra-only."
  }
  assert {
    condition     = jsonencode(azapi_resource.blob_service.body.properties) == jsonencode({ isVersioningEnabled = true, deleteRetentionPolicy = { enabled = true, days = 30 }, containerDeleteRetentionPolicy = { enabled = true, days = 30 } })
    error_message = "Production enables versioning and 30-day blob and container soft deletion."
  }
  assert {
    condition     = jsonencode(output.container_names) == jsonencode(["exports", "uploads"])
    error_message = "Only requested containers are created; the output is deterministic."
  }
  assert {
    condition     = azapi_resource.endpoint[0].body.properties.subnet.id == var.private_endpoint.subnet_id && jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["blob"]) && azapi_resource.dns_zone_group[0].body.properties.privateDnsZoneConfigs[0].properties.privateDnsZoneId == var.private_endpoint.private_dns_zone_id
    error_message = "The endpoint uses the supplied subnet and blob private DNS zone."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties) == jsonencode({ workspaceId = var.log_analytics_workspace_id, logs = [{ category = "StorageRead", enabled = true }, { category = "StorageWrite", enabled = true }, { category = "StorageDelete", enabled = true }], metrics = [{ category = "Transaction", enabled = true }] })
    error_message = "Blob reads, writes, deletes and transaction metrics go to the supplied workspace."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must create its account-scoped deletion lock."
  }
  assert {
    condition     = length(azapi_resource.account_blob_contributor) == 0 && jsonencode(keys(azapi_resource.container_blob_contributor)) == jsonencode(["exports", "uploads"])
    error_message = "With managed containers, the runtime identity is granted on each container, not the account."
  }
  assert {
    condition     = alltrue([for key, grant in azapi_resource.container_blob_contributor : grant.parent_id == azapi_resource.container[key].id])
    error_message = "Each grant is scoped to its own container."
  }
  assert {
    condition     = azapi_resource.container_blob_contributor["uploads"].name == "7f7ae395-db58-560e-ad5e-24f4d3476cfe" && azapi_resource.container_blob_contributor["exports"].name == "eda4d73d-a660-53ce-8726-0f7631a43caf"
    error_message = "Container grants use the Bicep guid(scope, principal, role) names."
  }
  assert {
    condition     = alltrue([for grant in azapi_resource.container_blob_contributor : jsonencode(grant.body.properties) == jsonencode({ roleDefinitionId = "/subscriptions/00000000-0000-0000-0000-000000000000/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe", principalId = var.principal_id, principalType = "ServicePrincipal" })])
    error_message = "The runtime service principal gets Storage Blob Data Contributor on each container."
  }
}

run "private_test" {
  command = plan
  variables {
    stage      = "test"
    containers = ["uploads"]
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/storage"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.account.body.properties.publicNetworkAccess == "Disabled" && length(azapi_resource.endpoint) == 1 && length(azapi_resource.dns_zone_group) == 1 && length(azapi_resource.diagnostics) == 1
    error_message = "Private networking and diagnostics are also available outside production."
  }
  assert {
    condition     = azapi_resource.account.body.sku.name == "Standard_LRS" && length(azapi_resource.protection) == 0 && jsonencode(output.container_names) == jsonencode(["uploads"])
    error_message = "Optional networking does not turn test into production."
  }
}

run "reject_short_principal" {
  command = plan
  variables {
    principal_id = "00000000"
  }
  expect_failures = [var.principal_id]
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
    condition     = !contains(keys(azapi_resource.account.body.properties), "publicNetworkAccess") && jsonencode(azapi_resource.account.body.properties.networkAcls) == jsonencode({ defaultAction = "Deny", ipRules = [{ value = "203.0.113.0/24", action = "Allow" }] })
    error_message = "The public opt-in must deny all but the allow list."
  }
}

run "reject_wrong_private_zone" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/storage"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.file.core.windows.net"
    }
  }
  expect_failures = [var.private_endpoint]
}
