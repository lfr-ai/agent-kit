locals {
  tags                   = { stage = var.stage }
  metrics_publisher_role = "3913510d-42f4-4e42-8a64-420c390055eb"
  # ARM guid() is UUIDv5 in this namespace, so assignment names match the Bicep source.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
  # Like Bicep subscriptionResourceId(): the resource group's subscription, not the provider's.
  subscription_scope      = "/subscriptions/${split("/", var.resource_group_id)[2]}"
  application_insights_id = var.application_insights_name == null ? null : "${var.resource_group_id}/providers/Microsoft.Insights/components/${var.application_insights_name}"
  with_insights           = var.application_insights_name == null ? 0 : 1

  # Optional fragments replace marker comments, so every policy file stays well-formed XML.
  token_validation = var.entra_tenant_id == null ? "" : replace(
    replace(file("${path.module}/../policies/validate-token.xml"), "{tenant-id}", var.entra_tenant_id),
    "{audience}",
    var.entra_audience
  )
  llm_tokens = var.llm_tokens_per_minute == 0 ? "" : replace(
    file("${path.module}/../policies/llm-tokens.xml"),
    "{tokens-per-minute}",
    tostring(var.llm_tokens_per_minute)
  )
  api_policy = replace(
    replace(
      replace(file("${path.module}/../policies/api.xml"), "<!-- validate-token -->", trimspace(local.token_validation)),
      "<!-- llm-tokens -->",
      trimspace(local.llm_tokens)
    ),
    "{requests-per-minute}",
    tostring(var.requests_per_minute)
  )
}

# Basic v2 is the dev/test tier. Production uses Standard v2: Microsoft's production v2 tier,
# with inbound private endpoints for an optional operator-owned edge and outbound VNet integration.
# Staging keeps Basic v2 for cost; it shares the production token and workspace guards, not the tier.
resource "azapi_resource" "service" {
  type      = "Microsoft.ApiManagement/service@2024-05-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  identity {
    type = "SystemAssigned"
  }
  body = {
    sku = {
      name     = var.stage == "prod" ? "StandardV2" : "BasicV2"
      capacity = 1
    }
    properties = {
      publisherEmail = var.publisher_email
      # Required by the API; shown only in the developer portal and notification emails.
      publisherName = var.name
    }
  }
  response_export_values = ["properties.gatewayUrl"]
}

resource "azapi_resource" "api" {
  type      = "Microsoft.ApiManagement/service/apis@2024-05-01"
  name      = "backend"
  parent_id = azapi_resource.service.id
  body = {
    properties = {
      displayName = "Backend"
      path        = ""
      serviceUrl  = var.backend_url
      protocols   = ["https"]
      # Callers are identified by Entra tokens, never by subscription keys.
      subscriptionRequired = false
    }
  }
  response_export_values = []
}

# Wildcard operations forward every path; an API without operations answers 404.
resource "azapi_resource" "operations" {
  for_each  = toset(["GET", "POST", "PUT", "PATCH", "DELETE"])
  type      = "Microsoft.ApiManagement/service/apis/operations@2024-05-01"
  name      = lower(each.key)
  parent_id = azapi_resource.api.id
  body = {
    properties = {
      displayName = each.key
      method      = each.key
      urlTemplate = "/*"
    }
  }
  response_export_values = []
}

resource "azapi_resource" "policy" {
  type                   = "Microsoft.ApiManagement/service/apis/policies@2024-05-01"
  name                   = "policy"
  parent_id              = azapi_resource.api.id
  body                   = { properties = { value = local.api_policy } }
  response_export_values = []
}

data "azapi_resource" "application_insights" {
  count                  = local.with_insights
  type                   = "Microsoft.Insights/components@2020-02-02"
  name                   = var.application_insights_name
  parent_id              = var.resource_group_id
  response_export_values = ["properties.ConnectionString"]
}

# The logger authenticates with the system identity, so ingestion needs no key.
resource "azapi_resource" "metrics_publisher" {
  count     = local.with_insights
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = uuidv5(local.guid_namespace, "${local.application_insights_id}-${azapi_resource.service.id}-${local.metrics_publisher_role}")
  parent_id = local.application_insights_id
  body = {
    properties = {
      roleDefinitionId = "${local.subscription_scope}/providers/Microsoft.Authorization/roleDefinitions/${local.metrics_publisher_role}"
      principalId      = azapi_resource.service.identity[0].principal_id
      principalType    = "ServicePrincipal"
    }
  }
  response_export_values = []
}

resource "azapi_resource" "logger" {
  count     = local.with_insights
  type      = "Microsoft.ApiManagement/service/loggers@2024-05-01"
  name      = "application-insights"
  parent_id = azapi_resource.service.id
  body = {
    properties = {
      loggerType = "applicationInsights"
      resourceId = local.application_insights_id
      credentials = {
        # Read from the component, never a variable; it identifies the target, it does not authorize.
        connectionString = data.azapi_resource.application_insights[0].output.properties.ConnectionString
        identityClientId = "SystemAssigned"
      }
    }
  }
  response_export_values = []
  depends_on             = [azapi_resource.metrics_publisher]
}

# metrics = true lets llm-emit-token-metric publish custom metrics.
resource "azapi_resource" "telemetry" {
  count     = local.with_insights
  type      = "Microsoft.ApiManagement/service/diagnostics@2024-05-01"
  name      = "applicationinsights"
  parent_id = azapi_resource.service.id
  body = {
    properties = {
      loggerId = azapi_resource.logger[0].id
      metrics  = true
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  count     = var.log_analytics_workspace_id == null ? 0 : 1
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "gateway-logs"
  parent_id = azapi_resource.service.id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      # Resource-specific ApiManagementGatewayLogs table instead of AzureDiagnostics.
      logAnalyticsDestinationType = "Dedicated"
      logs                        = [{ category = "GatewayLogs", enabled = true }]
    }
  }
  response_export_values = []
}

# Resource-scoped: never protects unrelated resources in the caller's group.
resource "azapi_resource" "protection" {
  count                  = var.stage == "prod" ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.service.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
