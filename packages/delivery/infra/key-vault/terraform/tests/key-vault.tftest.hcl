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
  name              = "sample-dev-kv"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  principal_id = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan

  assert {
    condition     = jsonencode(keys(azapi_resource.vault.body.properties)) == jsonencode(["enableRbacAuthorization", "enableSoftDelete", "publicNetworkAccess", "sku", "tenantId"])
    error_message = "Development declares RBAC and soft delete, and disables public access without purge protection."
  }
  assert {
    condition     = azapi_resource.vault.body.properties.publicNetworkAccess == "Disabled"
    error_message = "Development without an opt-in must disable public network access."
  }
  assert {
    condition     = azapi_resource.secrets_user.body.properties.principalId == var.principal_id && endswith(azapi_resource.secrets_user.body.properties.roleDefinitionId, "/4633458b-17de-408a-b874-0445c86b69e6")
    error_message = "Only the supplied identity receives Key Vault Secrets User."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.protection) == 0 && length(azapi_resource.diagnostics) == 0
    error_message = "Development without optional inputs must not create network, diagnostic or lock resources."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    name  = "sample-prod-kv"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/vault"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.vault.body.properties.enablePurgeProtection == true && azapi_resource.vault.body.properties.publicNetworkAccess == "Disabled"
    error_message = "Production must enable purge protection and disable public network access."
  }
  assert {
    condition     = jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["vault"]) && length(azapi_resource.dns_zone_group) == 1
    error_message = "Production must be reachable through the private endpoint and register private DNS."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties.logs) == jsonencode([{ category = "AuditEvent", enabled = true }])
    error_message = "Production must send AuditEvent logs to the workspace."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must lock the vault."
  }
}

run "development_allow_list" {
  command = plan
  variables {
    allow_public_network_access = true
    allowed_ip_ranges           = ["203.0.113.0/24"]
  }
  assert {
    condition     = !contains(keys(azapi_resource.vault.body.properties), "publicNetworkAccess") && jsonencode(azapi_resource.vault.body.properties.networkAcls) == jsonencode({ defaultAction = "Deny", ipRules = [{ value = "203.0.113.0/24" }] })
    error_message = "The public opt-in must deny all but the allow list."
  }
}

run "staging" {
  command = plan
  variables {
    stage = "staging"
    name  = "sample-stg-kv"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/vault"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.vault.body.properties.enablePurgeProtection == true && azapi_resource.vault.body.properties.publicNetworkAccess == "Disabled"
    error_message = "Staging must enable purge protection and disable public network access."
  }
  assert {
    condition     = length(azapi_resource.protection) == 0
    error_message = "Only production locks the vault."
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

run "reject_wrong_dns_zone" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/vault"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
    }
  }
  expect_failures = [var.private_endpoint]
}
