# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  name_prefix       = "sample-dev"
  stage             = "dev"
  # Synthetic ID: not a real app.
  container_app_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.App/containerApps/sample-dev"
}

run "development_unmonitored" {
  command = plan
  variables {
    unmonitored = true
  }

  assert {
    condition     = length(azapi_resource.notify) == 0 && length(local.alert_actions) == 0 && output.action_group_id == null
    error_message = "Unmonitored creates no action group, the rules notify nobody and the output is null."
  }
  assert {
    condition     = azapi_resource.restarts.body.properties.criteria.allOf[0].metricName == "RestartCount" && azapi_resource.restarts.body.properties.criteria.allOf[0].timeAggregation == "Maximum" && azapi_resource.restarts.body.properties.autoMitigate && length(azapi_resource.restarts.body.properties.actions) == 0
    error_message = "The restart alert uses the maximum cumulative restart count and states auto-resolve."
  }
  assert {
    condition     = jsonencode(azapi_resource.server_errors.body.properties.criteria.allOf[0].dimensions) == jsonencode([{ name = "statusCodeCategory", operator = "Include", values = ["5xx"] }]) && azapi_resource.server_errors.body.properties.autoMitigate
    error_message = "The 5xx alert filters Requests on the 5xx status code category and states auto-resolve."
  }
  assert {
    condition = alltrue([
      for rule in [azapi_resource.restarts, azapi_resource.server_errors] :
      rule.body.properties.severity == 2 && rule.body.properties.evaluationFrequency == "PT1M" && rule.body.properties.windowSize == "PT5M"
    ])
    error_message = "Both rules share the named Warning severity and one-minute/five-minute evaluation policy."
  }
  assert {
    condition = alltrue([
      azapi_resource.restarts.body.properties.criteria.allOf[0].threshold == 3,
      azapi_resource.restarts.body.properties.description == "A replica restarted more than 3 times: crash loop or failing probes.",
      azapi_resource.server_errors.body.properties.criteria.allOf[0].threshold == 5,
      azapi_resource.server_errors.body.properties.description == "More than 5 HTTP 5xx responses in 5 minutes.",
    ])
    error_message = "Descriptions are generated from the named thresholds and window."
  }
}

run "development_email" {
  command = plan
  variables {
    email_receivers = ["operations@example.com"]
  }

  assert {
    condition     = azapi_resource.notify[0].location == "global" && azapi_resource.notify[0].body.properties.groupShortName == "sample-dev" && length(azapi_resource.notify[0].body.properties.emailReceivers) == 1
    error_message = "Email receivers create one global action group."
  }
}

run "production" {
  command = plan
  variables {
    stage           = "prod"
    name_prefix     = "operations-prod"
    email_receivers = ["operations@example.com"]
  }
  assert {
    condition     = azapi_resource.notify[0].body.properties.groupShortName == "operations-p" && azapi_resource.notify[0].body.properties.emailReceivers[0].emailAddress == "operations@example.com"
    error_message = "Production notifies the email receivers under a 12-character short name."
  }
  assert {
    condition     = !can(azapi_resource.notify[0].body.properties.webhookReceivers)
    error_message = "The module never carries webhook receivers."
  }
}

run "reject_development_without_destination" {
  command         = plan
  expect_failures = [var.unmonitored]
}

run "reject_production_without_receivers" {
  command = plan
  variables {
    stage = "prod"
  }
  expect_failures = [var.unmonitored]
}

run "reject_staging_without_receivers" {
  command = plan
  variables {
    stage = "staging"
  }
  expect_failures = [var.unmonitored]
}

run "reject_unmonitored_in_production" {
  command = plan
  variables {
    stage       = "prod"
    unmonitored = true
  }
  expect_failures = [var.unmonitored]
}

run "reject_unmonitored_in_staging" {
  command = plan
  variables {
    stage       = "staging"
    unmonitored = true
  }
  expect_failures = [var.unmonitored]
}

run "existing_action_group" {
  command = plan
  variables {
    stage                             = "prod"
    existing_action_group_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/alerts/providers/Microsoft.Insights/actionGroups/operations"
  }
  assert {
    condition     = length(azapi_resource.notify) == 0
    error_message = "Referencing an existing group must not create a group."
  }
  assert {
    condition = alltrue([
      azapi_resource.restarts.body.properties.actions[0].actionGroupId == var.existing_action_group_resource_id,
      azapi_resource.server_errors.body.properties.actions[0].actionGroupId == var.existing_action_group_resource_id,
      output.action_group_id == var.existing_action_group_resource_id,
    ])
    error_message = "Every alarm and the output must reuse the supplied group ID."
  }
}

run "reject_existing_group_with_inline_receivers" {
  command = plan
  variables {
    existing_action_group_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/alerts/providers/Microsoft.Insights/actionGroups/operations"
    email_receivers                   = ["ops@example.com"]
  }
  expect_failures = [var.unmonitored]
}

run "reject_existing_group_with_unmonitored" {
  command = plan
  variables {
    existing_action_group_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/alerts/providers/Microsoft.Insights/actionGroups/operations"
    unmonitored                       = true
  }
  expect_failures = [var.unmonitored]
}

# Omission (null) is the only absent form; an empty string is not a destination.
run "reject_empty_existing_group" {
  command = plan
  variables {
    existing_action_group_resource_id = ""
  }
  expect_failures = [var.existing_action_group_resource_id]
}
