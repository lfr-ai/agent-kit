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
  description = "Azure region for the Foundry resource, its project and the optional private endpoint."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Globally unique name; also the custom subdomain and the project name."
  nullable    = false
  validation {
    condition     = length(var.name) >= 2 && length(var.name) <= 64
    error_message = "name must be 2-64 characters."
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

variable "principal_id" {
  type        = string
  description = "Object (principal) ID of the existing app identity that calls the models."
  nullable    = false
}

variable "deployments" {
  type = list(object({
    name     = string
    model    = string
    version  = string
    sku      = string
    capacity = number
    format   = optional(string, "OpenAI")
  }))
  description = "Model deployments; none by default. Model, version and quota are regional."
  default     = []
  nullable    = false
}

variable "private_endpoint" {
  type = object({
    subnet_id            = string
    private_dns_zone_ids = list(string)
  })
  description = "Existing subnet and the three Foundry private DNS zones; required in staging and production."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.private_endpoint != null
    error_message = "Staging and production require privateEndpoint: an existing subnet and the three Foundry private DNS zones."
  }
  validation {
    # || does not short-circuit, hence try(); IDs match the exact ARM shape and casing.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+/subnets/[^/]+$", try(var.private_endpoint.subnet_id, ""))) &&
      try(alltrue([for id in var.private_endpoint.private_dns_zone_ids : can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/[^/]+$", id))]), false) &&
      try(join(",", sort([for id in var.private_endpoint.private_dns_zone_ids : reverse(split("/", id))[0]])), "") ==
      "privatelink.cognitiveservices.azure.com,privatelink.openai.azure.com,privatelink.services.ai.azure.com"
    )
    error_message = "privateEndpoint needs a subnet ARM ID and the privatelink.cognitiveservices.azure.com, privatelink.openai.azure.com and privatelink.services.ai.azure.com private DNS zone ARM IDs."
  }
}

variable "allow_public_network_access" {
  type        = bool
  description = "Dev or test without private_endpoint only: keep the public endpoint, denying all but allowed_ip_ranges."
  default     = false
  nullable    = false
  validation {
    condition     = !var.allow_public_network_access || (var.private_endpoint == null && !contains(["staging", "prod"], var.stage))
    error_message = "allowPublicNetworkAccess is only for dev or test without privateEndpoint."
  }
}

variable "allowed_ip_ranges" {
  type        = list(string)
  description = "IPv4 addresses or CIDR ranges the network ACL allows with allow_public_network_access."
  default     = []
  nullable    = false
  validation {
    condition     = var.allow_public_network_access || length(var.allowed_ip_ranges) == 0
    error_message = "allowedIpRanges needs allowPublicNetworkAccess."
  }
  validation {
    condition     = alltrue([for value in var.allowed_ip_ranges : can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}(/[0-9]{1,2})?$", value))])
    error_message = "allowedIpRanges must hold IPv4 addresses or CIDR ranges, such as 203.0.113.0/24."
  }
}

variable "allow_all_public_clients" {
  type        = bool
  description = "With allow_public_network_access and no allowed_ip_ranges: allow every client network. Local keys stay disabled, so callers still need Entra tokens and a role. For dev callers without fixed egress, such as Container Apps outside a virtual network."
  default     = false
  nullable    = false
  validation {
    condition     = !var.allow_all_public_clients || (var.allow_public_network_access && length(var.allowed_ip_ranges) == 0)
    error_message = "allowAllPublicClients needs allowPublicNetworkAccess and no allowedIpRanges."
  }
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "Existing Log Analytics workspace ARM ID for resource logs and metrics; required in staging and production."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.log_analytics_workspace_id != null
    error_message = "Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for diagnostics."
  }
  validation {
    condition     = var.log_analytics_workspace_id == null || try(length(var.log_analytics_workspace_id) > 0, false)
    error_message = "logAnalyticsWorkspaceId must be omitted or non-empty."
  }
}
