# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sampledevtfstate"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  principal_id = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan

  assert {
    condition = azapi_resource.account.body.sku.name == "Standard_ZRS" && jsonencode(azapi_resource.account.body.properties) == jsonencode({
      allowSharedKeyAccess  = false
      allowBlobPublicAccess = false
      minimumTlsVersion     = "TLS1_2"
      networkAcls           = { defaultAction = "Deny", ipRules = [] }
    })
    error_message = "State storage is Entra-only, has no anonymous blob access, TLS 1.2, zone-redundant and firewalled deny-by-default; no other setting is restated."
  }
  assert {
    condition     = azapi_resource.blob_service.body.properties.isVersioningEnabled == true && azapi_resource.blob_service.body.properties.deleteRetentionPolicy.enabled == true && azapi_resource.blob_service.body.properties.containerDeleteRetentionPolicy.enabled == true
    error_message = "State blobs must be versioned and recoverable after deletion."
  }
  assert {
    condition     = azapi_resource.blob_service.body.properties.deleteRetentionPolicy.days == 30 && azapi_resource.blob_service.body.properties.containerDeleteRetentionPolicy.days == 30
    error_message = "Deleted state blobs and containers stay recoverable for 30 days."
  }
  assert {
    condition     = azapi_resource.container.name == "tfstate" && azapi_resource.state_writer.body.properties.principalId == var.principal_id && endswith(azapi_resource.state_writer.body.properties.roleDefinitionId, "/ba92f5b4-2d11-453d-a403-e96b0029c9fe")
    error_message = "Only the supplied CI identity receives Storage Blob Data Contributor on the tfstate container."
  }
  assert {
    condition     = length(azapi_resource.protection) == 0 && length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0
    error_message = "Development must not lock the account or create a private endpoint by default."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    name  = "sampleprodtfstate"
    sku   = "Standard_GZRS"
  }
  assert {
    condition     = azapi_resource.account.body.sku.name == "Standard_GZRS"
    error_message = "Production keeps the chosen zone-redundant replication."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must lock the state account."
  }
  assert {
    condition     = azapi_resource.account.body.properties.allowBlobPublicAccess == false && azapi_resource.account.body.properties.allowSharedKeyAccess == false
    error_message = "Production state never allows anonymous blob access or Shared Key."
  }
}

run "reject_production_lrs" {
  command = plan
  variables {
    stage = "prod"
    sku   = "Standard_LRS"
  }
  expect_failures = [var.sku]
}

run "reject_staging_lrs" {
  command = plan
  variables {
    stage = "staging"
    sku   = "Standard_LRS"
  }
  expect_failures = [var.sku]
}

run "staging" {
  command = plan
  variables {
    stage = "staging"
    name  = "samplestagingtfstate"
  }
  assert {
    condition     = azapi_resource.account.body.sku.name == "Standard_ZRS" && length(azapi_resource.protection) == 0
    error_message = "Staging keeps zone-redundant state without the production lock."
  }
}

run "allow_list" {
  command = plan
  variables {
    allowed_ip_ranges = ["203.0.113.0/24", "198.51.100.7"]
  }
  assert {
    condition = jsonencode(azapi_resource.account.body.properties.networkAcls) == jsonencode({
      defaultAction = "Deny"
      ipRules       = [{ value = "203.0.113.0/24", action = "Allow" }, { value = "198.51.100.7", action = "Allow" }]
    })
    error_message = "The firewall denies everything except the explicit allow list."
  }
}

run "private_endpoint" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/state"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    }
  }
  assert {
    condition     = azapi_resource.account.body.properties.publicNetworkAccess == "Disabled" && !contains(keys(azapi_resource.account.body.properties), "networkAcls") && azapi_resource.account.body.properties.allowBlobPublicAccess == false
    error_message = "A private endpoint disables public network access."
  }
  assert {
    condition     = jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["blob"]) && length(azapi_resource.dns_zone_group) == 1
    error_message = "The private endpoint targets the blob sub-resource and registers private DNS."
  }
}

run "reject_allow_list_with_private_endpoint" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/state"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    }
    allowed_ip_ranges = ["203.0.113.0/24"]
  }
  expect_failures = [var.allowed_ip_ranges]
}
