# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      # Synthetic value: the connection string identifies a component; it is not a credential.
      output = { properties = { ConnectionString = "InstrumentationKey=00000000-0000-0000-0000-000000000000" } }
    }
  }
}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-apim-dev"
  stage             = "dev"
  publisher_email   = "platform@example.com"
  backend_url       = "https://sample-app.example.com"
}

run "development" {
  command = plan

  assert {
    condition     = azapi_resource.service.body.sku.name == "BasicV2" && azapi_resource.service.identity[0].type == "SystemAssigned"
    error_message = "Development uses Basic v2 with a system-assigned identity."
  }
  assert {
    condition     = azapi_resource.api.body.properties.serviceUrl == var.backend_url && azapi_resource.api.body.properties.subscriptionRequired == false
    error_message = "The API fronts the backend without subscription keys."
  }
  assert {
    condition     = length(azapi_resource.operations) == 5 && alltrue([for operation in azapi_resource.operations : operation.body.properties.urlTemplate == "/*"])
    error_message = "Wildcard operations must forward every path."
  }
  assert {
    condition     = strcontains(local.api_policy, "<rate-limit-by-key calls=\"120\" renewal-period=\"60\"") && !strcontains(local.api_policy, "validate-azure-ad-token") && !strcontains(local.api_policy, "llm-token-limit")
    error_message = "Development rate limits per caller and leaves the optional policies out."
  }
  assert {
    condition     = !strcontains(local.api_policy, "<!--") && !strcontains(local.api_policy, "{")
    error_message = "Every marker and placeholder must be replaced."
  }
  assert {
    condition     = length(azapi_resource.logger) == 0 && length(azapi_resource.metrics_publisher) == 0 && length(azapi_resource.telemetry) == 0 && local.application_insights_id == null
    error_message = "Development without Application Insights must not create telemetry resources."
  }
  assert {
    condition     = length(azapi_resource.diagnostics) == 0 && length(azapi_resource.protection) == 0
    error_message = "Development without a workspace must not create diagnostics or a lock."
  }
}

run "production" {
  command = plan
  variables {
    name                       = "sample-apim-prod"
    stage                      = "prod"
    entra_tenant_id            = "00000000-0000-0000-0000-000000000000"
    entra_audience             = "api://sample-backend"
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.service.body.sku.name == "StandardV2"
    error_message = "Production uses Standard v2."
  }
  assert {
    condition     = strcontains(local.api_policy, "<validate-azure-ad-token tenant-id=\"${var.entra_tenant_id}\" output-token-variable-name=\"caller\">") && strcontains(local.api_policy, "<audience>api://sample-backend</audience>")
    error_message = "Production validates Entra tokens before rate limiting by subject."
  }
  assert {
    condition     = jsonencode(azapi_resource.diagnostics[0].body.properties.logs) == jsonencode([{ category = "GatewayLogs", enabled = true }]) && azapi_resource.diagnostics[0].body.properties.workspaceId == var.log_analytics_workspace_id
    error_message = "Production must send gateway logs to the workspace."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must lock the instance."
  }
}

run "ai_gateway_with_application_insights" {
  command = plan
  variables {
    llm_tokens_per_minute     = 5000
    application_insights_name = "sample-insights"
  }
  assert {
    condition     = strcontains(local.api_policy, "<llm-token-limit tokens-per-minute=\"5000\" estimate-prompt-tokens=\"false\"") && strcontains(local.api_policy, "<llm-emit-token-metric>")
    error_message = "The AI gateway option limits and reports LLM tokens."
  }
  assert {
    condition     = azapi_resource.metrics_publisher[0].parent_id == "${var.resource_group_id}/providers/Microsoft.Insights/components/sample-insights" && endswith(azapi_resource.metrics_publisher[0].body.properties.roleDefinitionId, "/3913510d-42f4-4e42-8a64-420c390055eb")
    error_message = "The identity publishes metrics to the named component only."
  }
  assert {
    condition     = azapi_resource.logger[0].body.properties.resourceId == azapi_resource.metrics_publisher[0].parent_id && azapi_resource.telemetry[0].body.properties.metrics == true
    error_message = "The logger and diagnostic must target the component with custom metrics on."
  }
}

run "staging" {
  command = plan
  variables {
    name                       = "sample-apim-staging"
    stage                      = "staging"
    entra_tenant_id            = "00000000-0000-0000-0000-000000000000"
    entra_audience             = "api://sample-backend"
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example"
  }
  assert {
    condition     = azapi_resource.service.body.sku.name == "BasicV2" && length(azapi_resource.protection) == 0
    error_message = "Staging keeps Basic v2 and no lock."
  }
  assert {
    condition     = strcontains(local.api_policy, "validate-azure-ad-token") && length(azapi_resource.diagnostics) == 1
    error_message = "Staging validates Entra tokens and sends gateway logs to the workspace."
  }
}

run "reject_staging_defaults" {
  command = plan
  variables {
    stage = "staging"
  }
  expect_failures = [var.entra_tenant_id, var.log_analytics_workspace_id]
}

run "reject_production_defaults" {
  command = plan
  variables {
    stage = "prod"
  }
  expect_failures = [var.entra_tenant_id, var.log_analytics_workspace_id]
}

run "reject_unsafe_inputs" {
  command = plan
  variables {
    backend_url           = "http://sample-app.example.com"
    entra_audience        = "api://sample-backend"
    llm_tokens_per_minute = 5000
  }
  expect_failures = [var.backend_url, var.entra_tenant_id, var.llm_tokens_per_minute]
}

run "reject_empty_optional_inputs" {
  command = plan
  variables {
    entra_tenant_id            = ""
    entra_audience             = ""
    application_insights_name  = ""
    log_analytics_workspace_id = ""
  }
  expect_failures = [var.entra_tenant_id, var.application_insights_name, var.log_analytics_workspace_id]
}
