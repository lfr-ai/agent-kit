# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-docs-dev"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  principal_id = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan
  # A realistic ARM ID makes the role-assignment name checkable against Bicep guid().
  override_resource {
    target          = azapi_resource.account
    override_during = plan
    values = {
      id     = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.CognitiveServices/accounts/sample-docs-dev"
      output = { properties = { endpoint = "https://sample-docs-dev.cognitiveservices.azure.com/" } }
    }
  }

  assert {
    condition = azapi_resource.account.body.kind == "FormRecognizer" && jsonencode(azapi_resource.account.body.properties) == jsonencode({
      customSubDomainName = var.name
      disableLocalAuth    = true
      publicNetworkAccess = "Disabled"
    })
    error_message = "Development keeps Entra-only access on a custom subdomain and is private by default."
  }
  assert {
    condition     = endswith(azapi_resource.analyze_access.body.properties.roleDefinitionId, "/a97b65f3-24c7-4388-baec-2e87135dc908") && azapi_resource.analyze_access.body.properties.principalId == var.principal_id
    error_message = "Only the supplied identity receives Cognitive Services User."
  }
  assert {
    condition     = azapi_resource.analyze_access.name == "8e84a0b5-6c1f-5776-95dc-87eb5e90b328"
    error_message = "The role-assignment name matches Bicep guid() for the same scope, principal and role."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.protection) == 0 && length(azapi_resource.diagnostics) == 0
    error_message = "Development without optional inputs must not create network, diagnostics or lock resources."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/documents"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.account.body.properties.publicNetworkAccess == "Disabled" && jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["account"])
    error_message = "Production must be reachable only through the private endpoint."
  }
  assert {
    condition     = length(azapi_resource.dns_zone_group) == 1 && length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must register private DNS and lock the resource."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties.logs) == jsonencode([{ categoryGroup = "allLogs", enabled = true }]) && azapi_resource.diagnostics[0].body.properties.workspaceId == var.log_analytics_workspace_id
    error_message = "Production must export resource logs and metrics to the workspace."
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

run "staging" {
  command = plan
  variables {
    stage = "staging"
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/documents"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com"
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.account.body.properties.publicNetworkAccess == "Disabled" && length(azapi_resource.endpoint) == 1 && length(azapi_resource.diagnostics) == 1 && length(azapi_resource.protection) == 0
    error_message = "Staging is private with diagnostics but no production lock."
  }
}

run "development_allow_list" {
  command = plan
  variables {
    allow_public_network_access = true
    allowed_ip_ranges           = ["203.0.113.0/24"]
  }
  assert {
    condition     = azapi_resource.account.body.properties.publicNetworkAccess == "Enabled" && jsonencode(azapi_resource.account.body.properties.networkAcls) == jsonencode({ defaultAction = "Deny", ipRules = [{ value = "203.0.113.0/24" }] })
    error_message = "The public opt-in must deny all but the listed ranges."
  }
}

run "reject_wrong_dns_zone" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/documents"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com"
    }
  }
  expect_failures = [var.private_endpoint]
}
