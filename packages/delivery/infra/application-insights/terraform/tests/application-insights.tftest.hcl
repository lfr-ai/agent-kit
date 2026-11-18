# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-dev"
  stage             = "dev"
  # Synthetic IDs: not real resources.
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  principal_id               = "00000000-0000-0000-0000-000000000000"
}

run "development" {
  command = plan
  # A realistic ARM ID makes the role-assignment name checkable against Bicep guid().
  override_resource {
    target          = azapi_resource.component
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Insights/components/sample-dev"
      # Synthetic, not a real ingestion endpoint.
      output = { properties = { ConnectionString = "IngestionEndpoint=https://example.invalid/" } }
    }
  }

  assert {
    condition     = azapi_resource.component.body.kind == "web" && azapi_resource.component.body.properties.WorkspaceResourceId == var.log_analytics_workspace_id
    error_message = "Application Insights must be workspace-based."
  }
  assert {
    condition     = azapi_resource.component.body.properties.DisableLocalAuth == false
    error_message = "Development keeps instrumentation-key ingestion for local runs."
  }
  assert {
    condition     = endswith(azapi_resource.publisher.body.properties.roleDefinitionId, "/roleDefinitions/3913510d-42f4-4e42-8a64-420c390055eb") && azapi_resource.publisher.body.properties.principalId == var.principal_id
    error_message = "The app identity must get Monitoring Metrics Publisher in every stage."
  }
  assert {
    condition     = azapi_resource.publisher.name == "abc32c7b-9683-5858-8dd8-1a979c2734da"
    error_message = "The role-assignment name matches Bicep guid() for the same scope, principal and role."
  }
}

run "test_and_production" {
  command = plan
  variables {
    stage = "test"
  }
  assert {
    condition     = azapi_resource.component.body.properties.DisableLocalAuth
    error_message = "Test and production accept Entra ID authenticated ingestion only."
  }
}

run "reject_workspace_name" {
  command = plan
  variables {
    log_analytics_workspace_id = "example"
  }
  expect_failures = [var.log_analytics_workspace_id]
}
