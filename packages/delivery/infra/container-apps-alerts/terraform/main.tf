locals {
  tags         = { stage = var.stage }
  create_group = length(var.email_receivers) > 0
  # Null when unmonitored; the rules then notify nobody.
  action_group_id = local.create_group ? azapi_resource.notify[0].id : var.existing_action_group_resource_id
  alert_actions   = var.unmonitored ? [] : [{ actionGroupId = local.action_group_id }]

  # Alert policy, named once and shared by both rules. Severity 2 is Warning (0 is Critical, 4 Verbose).
  alert_severity = 2
  # Evaluate every minute over a sliding five-minute window (ISO 8601 durations).
  evaluation_frequency = "PT1M"
  window_minutes       = 5
  window_size          = "PT${local.window_minutes}M"
  # RestartCount is cumulative per replica: more than this many restarts is a crash loop.
  restart_threshold      = 3
  server_error_threshold = 5
}

# Preserve the owned action group's address when upgrading with the default input.
moved {
  from = azapi_resource.notify
  to   = azapi_resource.notify[0]
}

# Only non-defaults are declared: email keeps the default schema. Teams is configured
# by the operator inside a caller-owned action group (see REFERENCE.md).
resource "azapi_resource" "notify" {
  count     = local.create_group ? 1 : 0
  type      = "Microsoft.Insights/actionGroups@2023-01-01"
  name      = "${var.name_prefix}-notify"
  parent_id = var.resource_group_id
  location  = "global"
  tags      = local.tags
  body = {
    properties = {
      # Shown in SMS and email; at most 12 characters.
      groupShortName = substr(var.name_prefix, 0, 12)
      # Required by this API version.
      enabled        = true
      emailReceivers = [for i, address in var.email_receivers : { name = "email-${i}", emailAddress = address }]
    }
  }
  response_export_values = []
}

# RestartCount is cumulative per replica, so its maximum exposes a crash loop.
resource "azapi_resource" "restarts" {
  type      = "Microsoft.Insights/metricAlerts@2018-03-01"
  name      = "${var.name_prefix}-restarts"
  parent_id = var.resource_group_id
  location  = "global"
  tags      = local.tags
  body = {
    properties = {
      description = "A replica restarted more than ${local.restart_threshold} times: crash loop or failing probes."
      severity    = local.alert_severity
      # Required by this API version.
      enabled = true
      # Stated explicitly: the alert resolves itself when the condition clears.
      autoMitigate        = true
      scopes              = [var.container_app_resource_id]
      evaluationFrequency = local.evaluation_frequency
      windowSize          = local.window_size
      criteria = {
        "odata.type" = "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria"
        allOf = [{
          criterionType   = "StaticThresholdCriterion"
          name            = "restarts"
          metricName      = "RestartCount"
          timeAggregation = "Maximum"
          operator        = "GreaterThan"
          threshold       = local.restart_threshold
        }]
      }
      actions = local.alert_actions
    }
  }
  response_export_values = []
}

# Needs HTTP ingress; an app without ingress emits no Requests.
resource "azapi_resource" "server_errors" {
  type      = "Microsoft.Insights/metricAlerts@2018-03-01"
  name      = "${var.name_prefix}-5xx"
  parent_id = var.resource_group_id
  location  = "global"
  tags      = local.tags
  body = {
    properties = {
      description = "More than ${local.server_error_threshold} HTTP 5xx responses in ${local.window_minutes} minutes."
      severity    = local.alert_severity
      # Required by this API version.
      enabled = true
      # Stated explicitly: the alert resolves itself when the condition clears.
      autoMitigate        = true
      scopes              = [var.container_app_resource_id]
      evaluationFrequency = local.evaluation_frequency
      windowSize          = local.window_size
      criteria = {
        "odata.type" = "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria"
        allOf = [{
          criterionType   = "StaticThresholdCriterion"
          name            = "server-errors"
          metricName      = "Requests"
          dimensions      = [{ name = "statusCodeCategory", operator = "Include", values = ["5xx"] }]
          timeAggregation = "Total"
          operator        = "GreaterThan"
          threshold       = local.server_error_threshold
        }]
      }
      actions = local.alert_actions
    }
  }
  response_export_values = []
}
