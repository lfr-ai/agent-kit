locals {
  subscription_id         = regex("^/subscriptions/[^/]+", var.resource_group_id)
  alert_on_access_changes = coalesce(var.alert_on_access_changes, contains(["staging", "prod"], var.stage))
  tags                    = { stage = var.stage }
  notify                  = { actionGroups = [{ actionGroupId = var.action_group_id }] }
  # Recommendation (Advisor) and Autoscale (classic autoscale settings) are left out.
  categories = ["Administrative", "Security", "Policy", "Alert", "ServiceHealth", "ResourceHealth"]
  access_operations = [
    "Microsoft.Authorization/roleAssignments/write",
    "Microsoft.Authorization/roleAssignments/delete",
    "Microsoft.Authorization/policyAssignments/write",
    "Microsoft.Authorization/policyAssignments/delete",
    "Microsoft.Authorization/policyExemptions/write",
    "Microsoft.Authorization/policyExemptions/delete",
  ]
}

# The export is a subscription resource; the alert rules live in the resource group.
resource "azapi_resource" "activity_log" {
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "audit-activity-log"
  parent_id = local.subscription_id
  body = {
    properties = {
      workspaceId = var.log_analytics_workspace_id
      logs        = [for category in local.categories : { category = category, enabled = true }]
    }
  }
  response_export_values = []
}

# Only non-defaults are declared: activity log alerts are enabled by default.
resource "azapi_resource" "service_health" {
  type      = "Microsoft.Insights/activityLogAlerts@2020-10-01"
  name      = "audit-service-health"
  parent_id = var.resource_group_id
  # 'global' is the default, declared so a caller's azapi default_location cannot move it.
  location = "global"
  tags     = local.tags
  body = {
    properties = {
      description = "Azure Service Health reports an incident, maintenance, advisory or security event for this subscription."
      scopes      = [local.subscription_id]
      condition   = { allOf = [{ field = "category", equals = "ServiceHealth" }] }
      actions     = local.notify
    }
  }
  response_export_values = []
}

resource "azapi_resource" "access_changes" {
  count     = local.alert_on_access_changes ? 1 : 0
  type      = "Microsoft.Insights/activityLogAlerts@2020-10-01"
  name      = "audit-access-changes"
  parent_id = var.resource_group_id
  location  = "global"
  tags      = local.tags
  body = {
    properties = {
      description = "A role assignment, policy assignment or policy exemption was created, changed or deleted."
      scopes      = [local.subscription_id]
      condition = {
        allOf = [
          { field = "category", equals = "Administrative" },
          # One alert per change, not one per Started/Accepted/Succeeded event.
          { field = "status", equals = "Succeeded" },
          { anyOf = [for operation in local.access_operations : { field = "operationName", equals = operation }] },
        ]
      }
      actions = local.notify
    }
  }
  response_export_values = []
}
