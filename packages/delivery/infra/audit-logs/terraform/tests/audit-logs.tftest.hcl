# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  stage             = "dev"
  # Synthetic IDs: not real resources.
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  action_group_id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.Insights/actionGroups/sample-dev-notify"
}

run "development" {
  command = plan

  assert {
    condition     = azapi_resource.activity_log.parent_id == "/subscriptions/00000000-0000-0000-0000-000000000000" && azapi_resource.activity_log.body.properties.workspaceId == var.log_analytics_workspace_id
    error_message = "The subscription Activity Log must be exported to the workspace."
  }
  assert {
    condition     = [for log in azapi_resource.activity_log.body.properties.logs : log.category] == ["Administrative", "Security", "Policy", "Alert", "ServiceHealth", "ResourceHealth"]
    error_message = "The export must keep the audit-relevant categories."
  }
  assert {
    condition     = azapi_resource.service_health.body.properties.scopes == ["/subscriptions/00000000-0000-0000-0000-000000000000"] && azapi_resource.service_health.body.properties.actions.actionGroups[0].actionGroupId == var.action_group_id
    error_message = "Service Health must alert the supplied action group for this subscription."
  }
  assert {
    condition     = length(azapi_resource.access_changes) == 0
    error_message = "Development does not alert on access changes by default."
  }
}

run "production" {
  command = plan
  variables {
    stage = "prod"
  }
  assert {
    condition     = length(azapi_resource.access_changes) == 1
    error_message = "Production alerts on role and policy changes by default."
  }
  assert {
    condition     = length(azapi_resource.access_changes[0].body.properties.condition.allOf[2].anyOf) == 6
    error_message = "The access alert must cover role assignments, policy assignments and policy exemptions."
  }
}

run "staging" {
  command = plan
  variables {
    stage = "staging"
  }
  assert {
    condition     = length(azapi_resource.access_changes) == 1
    error_message = "Staging alerts on role and policy changes by default."
  }
}

run "opt_out" {
  command = plan
  variables {
    stage                   = "prod"
    alert_on_access_changes = false
  }
  assert {
    condition     = length(azapi_resource.access_changes) == 0
    error_message = "An explicit false must disable the access alert."
  }
}

run "reject_action_group_name" {
  command = plan
  variables {
    action_group_id = "sample-dev-notify"
  }
  expect_failures = [var.action_group_id]
}
