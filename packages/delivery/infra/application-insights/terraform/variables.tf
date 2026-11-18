variable "resource_group_id" {
  type        = string
  description = "Existing resource group ID; this module does not own the group."
  nullable    = false
  validation {
    condition     = can(regex("^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+$", var.resource_group_id))
    error_message = "Supply a resource group ARM ID."
  }
}

variable "location" {
  type        = string
  description = "Azure region; normally the workspace region."
  nullable    = false
  validation {
    condition     = var.location != ""
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Application Insights resource name. Use a distinct name per stage."
  nullable    = false
  validation {
    condition     = var.name != ""
    error_message = "An Application Insights name is required."
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
  description = "ARM ID of the existing Log Analytics workspace that stores the telemetry."
  nullable    = false
  validation {
    condition     = startswith(lower(var.log_analytics_workspace_id), "/subscriptions/") && strcontains(lower(var.log_analytics_workspace_id), "/microsoft.operationalinsights/workspaces/")
    error_message = "logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID."
  }
}

variable "principal_id" {
  type        = string
  description = "Object (principal) ID of the existing app identity that publishes telemetry."
  nullable    = false
  validation {
    condition     = length(var.principal_id) == 36 && length(split("-", var.principal_id)) == 5
    error_message = "principalId must be the object (principal) ID GUID of the existing app identity."
  }
}
