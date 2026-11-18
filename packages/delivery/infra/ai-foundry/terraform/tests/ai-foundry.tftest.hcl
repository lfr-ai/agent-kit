# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "swedencentral"
  name              = "sample-foundry-dev"
  stage             = "dev"
  # Synthetic object ID: not a real identity.
  principal_id = "00000000-0000-0000-0000-000000000000"
  deployments = [{
    name     = "chat"
    model    = "example-model"
    version  = "1"
    sku      = "GlobalStandard"
    capacity = 1
  }]
}

run "development" {
  command = plan
  # Realistic ARM IDs make the role-assignment names checkable against Bicep guid().
  override_resource {
    target          = azapi_resource.foundry
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.CognitiveServices/accounts/sample-foundry-dev" }
  }
  override_resource {
    target          = azapi_resource.project
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.CognitiveServices/accounts/sample-foundry-dev/projects/sample-foundry-dev" }
  }

  assert {
    condition = azapi_resource.foundry.body.kind == "AIServices" && jsonencode(azapi_resource.foundry.body.properties) == jsonencode({
      allowProjectManagement = true
      customSubDomainName    = var.name
      disableLocalAuth       = true
      publicNetworkAccess    = "Disabled"
    })
    error_message = "Development keeps Entra-only access and project management, with public access disabled by default."
  }
  assert {
    condition     = azapi_resource.project.name == var.name && jsonencode(azapi_resource.project.body) == jsonencode({ properties = {} })
    error_message = "One project named after the resource, with no restated defaults."
  }
  assert {
    condition     = jsonencode(azapi_resource.model_deployment["chat"].body.properties.model) == jsonencode({ format = "OpenAI", name = "example-model", version = "1" })
    error_message = "Deployments default to the OpenAI format and pin the supplied version."
  }
  assert {
    condition     = endswith(azapi_resource.inference_access.body.properties.roleDefinitionId, "/5e0bd9bd-7b93-4f28-af87-19fc36ad61bd") && endswith(azapi_resource.project_access.body.properties.roleDefinitionId, "/53ca6127-db72-4b80-b1b0-d745d6d5456d")
    error_message = "The app gets Cognitive Services OpenAI User on the account and Foundry User on the project."
  }
  assert {
    condition     = azapi_resource.inference_access.name == "03b65ee8-12f1-53d9-a0b2-8adc1dc623fc" && azapi_resource.project_access.name == "d2903bdd-af6b-567a-a86b-dcb26dda42b9"
    error_message = "Role-assignment names match Bicep guid() for the same scope, principal and role."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && length(azapi_resource.protection) == 0 && length(azapi_resource.diagnostics) == 0
    error_message = "Development without optional inputs must not create network, diagnostics or lock resources."
  }
  assert {
    condition     = output.project_endpoint == "https://sample-foundry-dev.services.ai.azure.com/api/projects/sample-foundry-dev"
    error_message = "The project endpoint follows the documented format."
  }
}

run "production" {
  command = plan
  variables {
    stage       = "prod"
    deployments = []
    private_endpoint = {
      subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/foundry"
      private_dns_zone_ids = [
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com",
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com",
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.services.ai.azure.com",
      ]
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.foundry.body.properties.publicNetworkAccess == "Disabled" && jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["account"])
    error_message = "Production must be reachable only through the private endpoint."
  }
  assert {
    condition     = length(azapi_resource.dns_zone_group[0].body.properties.privateDnsZoneConfigs) == 3 && length(azapi_resource.model_deployment) == 0
    error_message = "Production registers all three Foundry zones and deploys no default model."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties.logs) == jsonencode([{ categoryGroup = "allLogs", enabled = true }]) && azapi_resource.diagnostics[0].body.properties.workspaceId == var.log_analytics_workspace_id
    error_message = "Production must export resource logs and metrics to the workspace."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must lock the Foundry resource."
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
      subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/foundry"
      private_dns_zone_ids = [
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com",
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com",
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.services.ai.azure.com",
      ]
    }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.foundry.body.properties.publicNetworkAccess == "Disabled" && length(azapi_resource.endpoint) == 1 && length(azapi_resource.diagnostics) == 1
    error_message = "Staging gets the production network and diagnostics guards."
  }
  assert {
    condition     = length(azapi_resource.protection) == 0
    error_message = "Staging is not locked, so it can be torn down freely."
  }
}

run "development_allow_list" {
  command = plan
  variables {
    deployments                 = []
    allow_public_network_access = true
    allowed_ip_ranges           = ["203.0.113.0/24"]
  }
  assert {
    condition = azapi_resource.foundry.body.properties.publicNetworkAccess == "Enabled" && jsonencode(azapi_resource.foundry.body.properties.networkAcls) == jsonencode({
      defaultAction = "Deny"
      ipRules       = [{ value = "203.0.113.0/24" }]
    })
    error_message = "The explicit public opt-in denies everything except the allow list."
  }
  assert {
    condition     = length(azapi_resource.model_deployment) == 0
    error_message = "An empty deployments list deploys no model."
  }
}

run "development_all_public_clients" {
  command = plan
  variables {
    deployments                 = []
    allow_public_network_access = true
    allow_all_public_clients    = true
  }
  assert {
    condition = azapi_resource.foundry.body.properties.publicNetworkAccess == "Enabled" && azapi_resource.foundry.body.properties.disableLocalAuth && jsonencode(azapi_resource.foundry.body.properties.networkAcls) == jsonencode({
      defaultAction = "Allow"
      ipRules       = []
    })
    error_message = "The all-clients opt-in keeps an Entra-only endpoint open to every network."
  }
}

run "reject_incomplete_dns_zones" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/foundry"
      private_dns_zone_ids = ["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com"]
    }
  }
  expect_failures = [var.private_endpoint]
}
