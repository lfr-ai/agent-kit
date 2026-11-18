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
  description = "Azure region for the API Management instance."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Globally unique name; the gateway is https://<name>.azure-api.net. Use a distinct name per stage."
  nullable    = false
  validation {
    condition     = length(var.name) >= 1 && length(var.name) <= 50
    error_message = "name must be 1-50 characters."
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

variable "publisher_email" {
  type        = string
  description = "Email address that receives API Management system notifications."
  nullable    = false
  validation {
    condition     = length(var.publisher_email) > 0
    error_message = "publisherEmail is required."
  }
}

variable "backend_url" {
  type        = string
  description = "HTTPS base URL of the backend the API fronts, for example a Container App URL."
  nullable    = false
  validation {
    condition     = startswith(var.backend_url, "https://") && length(var.backend_url) > 8
    error_message = "backendUrl must be an https:// URL."
  }
}

variable "entra_tenant_id" {
  type        = string
  description = "Entra tenant that issues caller tokens; set with entra_audience. Required in staging and production."
  default     = null
  validation {
    condition     = (var.entra_tenant_id == null) == (var.entra_audience == null)
    error_message = "entraTenantId and entraAudience must be set together."
  }
  validation {
    # A lone audience already fails the rule above.
    condition     = !contains(["staging", "prod"], var.stage) || var.entra_tenant_id != null || var.entra_audience != null
    error_message = "Staging and production require entraTenantId and entraAudience: callers must present an Entra token."
  }
  validation {
    # A lone value already fails the pair rule; the conditional skips length(null).
    condition     = var.entra_tenant_id == null || var.entra_audience == null ? true : length(var.entra_tenant_id) > 0 && length(var.entra_audience) > 0
    error_message = "entraTenantId and entraAudience must be omitted or non-empty."
  }
}

variable "entra_audience" {
  type        = string
  description = "Application ID URI or client ID that caller tokens must target; set with entra_tenant_id."
  default     = null
}

variable "requests_per_minute" {
  type        = number
  description = "Calls per minute for each caller: the token subject, or the client IP without token validation."
  default     = 120
  nullable    = false
  validation {
    condition     = var.requests_per_minute >= 1 && floor(var.requests_per_minute) == var.requests_per_minute
    error_message = "requestsPerMinute must be a whole number of at least 1."
  }
}

variable "llm_tokens_per_minute" {
  type        = number
  description = "LLM tokens per minute for each caller; 0 leaves the AI gateway policies out. Needs application_insights_name."
  default     = 0
  nullable    = false
  validation {
    condition     = var.llm_tokens_per_minute >= 0 && floor(var.llm_tokens_per_minute) == var.llm_tokens_per_minute
    error_message = "llmTokensPerMinute must be a whole number of at least 0."
  }
  validation {
    condition     = var.llm_tokens_per_minute == 0 || var.application_insights_name != null
    error_message = "llmTokensPerMinute needs applicationInsightsName to publish token metrics."
  }
}

variable "application_insights_name" {
  type        = string
  description = "Existing Application Insights component in this resource group for gateway telemetry; omit for none."
  default     = null
  validation {
    condition     = var.application_insights_name == null || try(length(var.application_insights_name) > 0, false)
    error_message = "applicationInsightsName must be omitted or non-empty."
  }
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "Existing Log Analytics workspace ARM ID for gateway logs; required in staging and production."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.log_analytics_workspace_id != null
    error_message = "Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for gateway logs."
  }
  validation {
    condition     = var.log_analytics_workspace_id == null || try(length(var.log_analytics_workspace_id) > 0, false)
    error_message = "logAnalyticsWorkspaceId must be omitted or non-empty."
  }
}
