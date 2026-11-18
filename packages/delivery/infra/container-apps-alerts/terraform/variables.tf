variable "resource_group_id" {
  type        = string
  description = "Existing resource group ID for the action group and alert rules; this module does not own the group."
  nullable    = false
  validation {
    condition     = can(regex("^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+$", var.resource_group_id))
    error_message = "Supply a resource group ARM ID."
  }
}

variable "name_prefix" {
  type        = string
  description = "Prefix for the action group and alert rule names. Use a distinct prefix per stage."
  nullable    = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,30}[a-z0-9]$", var.name_prefix)) && !strcontains(var.name_prefix, "--")
    error_message = "name must use 2-32 lowercase letters, digits or single hyphens; start with a letter and end alphanumeric."
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

variable "container_app_resource_id" {
  type        = string
  description = "ARM ID of the existing Container App to watch."
  nullable    = false
  validation {
    condition     = can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.App/containerApps/[^/]+$", var.container_app_resource_id)) && !can(regex("[[:space:]\\p{Z}\\x{0085}]", var.container_app_resource_id))
    error_message = "containerAppResourceId must be a Microsoft.App/containerApps ARM ID."
  }
}

variable "email_receivers" {
  type        = list(string)
  description = "Email addresses for an action group this module creates. Mutually exclusive with existing_action_group_resource_id and unmonitored."
  default     = []
  nullable    = false
  validation {
    condition     = alltrue([for address in var.email_receivers : can(regex("^[^@]+@[^@]+$", address)) && !can(regex("[[:space:]\\p{Z}\\x{0085}]", address))])
    error_message = "emailReceivers must be email addresses, for example ops@example.com."
  }
}

variable "existing_action_group_resource_id" {
  type        = string
  description = "Caller-owned action group ARM ID, for example one with a Teams workflow receiver. Its receivers are never read or managed. Mutually exclusive with email_receivers and unmonitored. Omit (null) when unused; an empty string is rejected."
  default     = null
  validation {
    condition     = var.existing_action_group_resource_id == null ? true : can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Insights/actionGroups/[^/]+$", var.existing_action_group_resource_id)) && !can(regex("[[:space:]\\p{Z}\\x{0085}]", var.existing_action_group_resource_id))
    error_message = "existingActionGroupResourceId must be an action group ARM ID."
  }
}

variable "unmonitored" {
  type        = bool
  description = "Explicit opt-out for dev and test only: the rules exist but notify nobody. Rejected for staging and prod."
  default     = false
  nullable    = false
  # Keep all destination relationships here to avoid a cross-variable validation cycle.
  validation {
    condition     = !var.unmonitored || !contains(["staging", "prod"], var.stage)
    error_message = "unmonitored is allowed only for dev and test; staging and production require emailReceivers or existingActionGroupResourceId."
  }
  validation {
    condition     = (length(var.email_receivers) > 0 ? 1 : 0) + (var.existing_action_group_resource_id != null ? 1 : 0) + (var.unmonitored ? 1 : 0) <= 1
    error_message = "emailReceivers, existingActionGroupResourceId and unmonitored are mutually exclusive; set exactly one."
  }
  validation {
    condition     = contains(["staging", "prod"], var.stage) || (length(var.email_receivers) > 0 ? 1 : 0) + (var.existing_action_group_resource_id != null ? 1 : 0) + (var.unmonitored ? 1 : 0) >= 1
    error_message = "Set exactly one of emailReceivers, existingActionGroupResourceId or unmonitored=true."
  }
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || length(var.email_receivers) > 0 || var.existing_action_group_resource_id != null || var.unmonitored
    error_message = "Staging and production require emailReceivers or existingActionGroupResourceId."
  }
}
