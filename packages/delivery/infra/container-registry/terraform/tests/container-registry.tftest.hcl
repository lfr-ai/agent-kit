# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sampledevacr"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  pull_principal_id = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan
  variables {
    # Basic cannot disable public access, so development opts in explicitly.
    allow_public_network_access = true
  }

  assert {
    condition     = azapi_resource.registry.body.sku.name == "Basic" && jsonencode(azapi_resource.registry.body.properties) == jsonencode({ adminUserEnabled = false, anonymousPullEnabled = false })
    error_message = "Development uses Basic, disables the admin user and anonymous pull explicitly and declares nothing else."
  }
  assert {
    condition     = azapi_resource.pull.body.properties.principalId == var.pull_principal_id && endswith(azapi_resource.pull.body.properties.roleDefinitionId, "/7f951dda-4ed3-4680-a7ca-43fe172d538d")
    error_message = "Only the supplied app identity receives AcrPull."
  }
  assert {
    condition     = length(azapi_resource.push) == 0 && length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0
    error_message = "Development without optional inputs must not grant push or create network resources."
  }
  assert {
    condition     = length(azapi_resource.diagnostics) == 0 && length(azapi_resource.protection) == 0
    error_message = "Development without a workspace must not create diagnostic or lock resources."
  }
}

run "production" {
  command = plan
  variables {
    stage             = "prod"
    name              = "sampleprodacr"
    sku               = "Premium"
    push_principal_id = "11111111-1111-1111-1111-111111111111"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/registry"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.registry.body.sku.name == "Premium" && azapi_resource.registry.body.properties.publicNetworkAccess == "Disabled"
    error_message = "Production must use Premium and disable public network access."
  }
  assert {
    condition     = azapi_resource.registry.body.properties.adminUserEnabled == false && azapi_resource.registry.body.properties.anonymousPullEnabled == false
    error_message = "Production must keep the admin user and anonymous pull disabled; Entra ID roles are the only credential."
  }
  assert {
    condition     = jsonencode(azapi_resource.registry.body.properties.policies) == jsonencode({ retentionPolicy = { status = "enabled" } })
    error_message = "Production must enable untagged-manifest retention with the default period."
  }
  assert {
    condition     = azapi_resource.push[0].body.properties.principalId == var.push_principal_id && endswith(azapi_resource.push[0].body.properties.roleDefinitionId, "/8311e382-0749-4cb8-b61a-304f252e45ec")
    error_message = "The CI identity receives AcrPush when supplied."
  }
  assert {
    condition     = jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["registry"]) && length(azapi_resource.dns_zone_group) == 1
    error_message = "Production must be reachable through the private endpoint and register private DNS."
  }
  assert {
    condition     = length(azapi_resource.diagnostics[0].body.properties.logs) == 2 && length(azapi_resource.protection) == 1
    error_message = "Production must send registry audit logs to the workspace and lock the registry."
  }
}

run "reject_production_basic_default" {
  command = plan
  variables {
    stage = "prod"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/registry"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  expect_failures = [var.sku]
}

run "reject_production_defaults" {
  command = plan
  variables {
    stage = "prod"
    # Premium isolates the missing inputs: Terraform 1.16 skips var.sku checks
    # that reference the invalid var.private_endpoint; see the run above.
    sku = "Premium"
  }
  expect_failures = [var.private_endpoint, var.log_analytics_workspace_id]
}

run "reject_staging_defaults" {
  command = plan
  variables {
    stage = "staging"
    sku   = "Premium"
  }
  expect_failures = [var.private_endpoint, var.log_analytics_workspace_id]
}

run "staging" {
  command = plan
  variables {
    stage = "staging"
    name  = "samplestagingacr"
    sku   = "Premium"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/registry"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = jsonencode(azapi_resource.registry.body.properties) == jsonencode({ adminUserEnabled = false, anonymousPullEnabled = false, publicNetworkAccess = "Disabled" })
    error_message = "Staging must disable public access without production retention."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 1 && length(azapi_resource.diagnostics) == 1 && length(azapi_resource.protection) == 0
    error_message = "Staging needs the private endpoint and audit logs but no production lock."
  }
}

run "development_premium_allow_list" {
  command = plan
  variables {
    sku                         = "Premium"
    allow_public_network_access = true
    allowed_ip_ranges           = ["203.0.113.0/24"]
  }
  assert {
    condition     = jsonencode(azapi_resource.registry.body.properties) == jsonencode({ adminUserEnabled = false, anonymousPullEnabled = false, networkRuleSet = { defaultAction = "Deny", ipRules = [{ action = "Allow", value = "203.0.113.0/24" }] } })
    error_message = "Premium public access must deny all but the allow list."
  }
}

run "development_premium_private_by_default" {
  command = plan
  variables {
    sku = "Premium"
  }
  assert {
    condition     = jsonencode(azapi_resource.registry.body.properties) == jsonencode({ adminUserEnabled = false, anonymousPullEnabled = false, publicNetworkAccess = "Disabled" })
    error_message = "Premium without the opt-in must disable public network access."
  }
}

run "reject_basic_without_public_opt_in" {
  command         = plan
  expect_failures = [var.sku]
}

run "reject_production_without_premium" {
  command = plan
  variables {
    stage = "prod"
    sku   = "Standard"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/registry"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  expect_failures = [var.sku]
}

run "reject_private_endpoint_without_premium" {
  command = plan
  variables {
    sku = "Standard"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/registry"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io"
    }
  }
  expect_failures = [var.sku]
}
