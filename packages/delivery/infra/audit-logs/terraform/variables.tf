variable "resource_group_id" {
  type        = string
  description = "Existing resource group ID for the alert rules; its subscription is the one audited."
  nullable    = false
  validation {
    condition     = can(regex("^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+$", var.resource_group_id))
    error_message = "Supply a resource group ARM ID."
  }
}

variable "stage" {
  type        = string
  description = "Deployment distinction, not inferred from a name or workspace."
  nullable    = false
  validation {
    condition     = contains(["dev", "test", "staging", "prod"], var.stage)
    error_message = "stage must be dev, test, staging or prod."
  }
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "ARM ID of the existing Log Analytics workspace that receives the subscription Activity Log."
  nullable    = false
  validation {
    condition     = startswith(lower(var.log_analytics_workspace_id), "/subscriptions/") && strcontains(lower(var.log_analytics_workspace_id), "/microsoft.operationalinsights/workspaces/")
    error_message = "logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID."
  }
}

variable "action_group_id" {
  type        = string
  description = "ARM ID of the existing action group that receives the alerts."
  nullable    = false
  validation {
    condition     = startswith(lower(var.action_group_id), "/subscriptions/") && strcontains(lower(var.action_group_id), "/microsoft.insights/actiongroups/")
    error_message = "actionGroupId must be an action group ARM ID, for example the container-apps-alerts output."
  }
}

variable "alert_on_access_changes" {
  type        = bool
  description = "Alert on role assignment, policy assignment and policy exemption changes. On by default in staging and prod."
  default     = null
}
