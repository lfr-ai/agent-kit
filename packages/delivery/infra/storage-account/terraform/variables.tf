variable "resource_group_id" {
  type        = string
  description = "Existing resource group ARM ID; this module does not own the group."
  nullable    = false
  validation {
    condition     = can(regex("^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+$", var.resource_group_id))
    error_message = "Supply a resource group ARM ID."
  }
}

variable "location" {
  type        = string
  description = "Azure region for the storage account and its optional private endpoint."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Globally unique storage account name; use a distinct name per stage."
  nullable    = false
  validation {
    condition     = can(regex("^[a-z0-9]{3,24}$", var.name))
    error_message = "name must be 3-24 lowercase letters and digits."
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
  description = "Object (principal) ID of the existing app identity that reads and writes blobs, not its client ID."
  nullable    = false
  validation {
    condition     = length(var.principal_id) == 36
    error_message = "principalId must be a 36-character object (principal) ID."
  }
}

variable "containers" {
  type        = list(string)
  description = "Unique private blob container names; empty creates none."
  default     = []
  nullable    = false
  validation {
    condition = alltrue([
      for name in var.containers :
      try(can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", name)) && !strcontains(name, "--"), false)
    ])
    error_message = "Container names must be 3-63 lowercase letters, digits or single hyphens, beginning and ending with a letter or digit."
  }
  validation {
    condition     = length(var.containers) == length(distinct(var.containers))
    error_message = "Container names must be unique."
  }
}

variable "private_endpoint" {
  type = object({
    subnet_id           = string
    private_dns_zone_id = string
  })
  description = "Existing subnet and privatelink.blob.core.windows.net zone; required in staging and production. Public network access is disabled unless allow_public_network_access is set."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.private_endpoint != null
    error_message = "Staging and production require privateEndpoint: an existing subnet and privatelink.blob.core.windows.net zone."
  }
  validation {
    # can() turns attribute access on null into false; the null case is allowed explicitly.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+/subnets/[^/]+$", var.private_endpoint.subnet_id)) &&
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/privatelink\\.blob\\.core\\.windows\\.net$", var.private_endpoint.private_dns_zone_id))
    )
    error_message = "privateEndpoint needs a subnet ARM ID and a privatelink.blob.core.windows.net private DNS zone ARM ID."
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
  description = "Public IPv4 addresses or CIDR ranges the firewall allows; needs allow_public_network_access. Storage rejects /31 and /32: pass a bare address."
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

variable "log_analytics_workspace_id" {
  type        = string
  description = "Existing Log Analytics workspace ARM ID for blob logs and metrics; required in staging and production."
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
