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
  description = "Azure region for the state storage account."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Globally unique storage account name: lowercase letters and digits. Use a distinct name per stage."
  nullable    = false
  validation {
    condition     = length(var.name) >= 3 && length(var.name) <= 24
    error_message = "name must be 3-24 characters."
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
  description = "Object (principal) ID of the existing CI identity that reads and writes state, not its client ID."
  nullable    = false
  validation {
    condition     = length(var.principal_id) == 36
    error_message = "principalId must be a 36-character object (principal) ID."
  }
}

variable "sku" {
  type        = string
  description = "Replication. Staging and production reject Standard_LRS."
  default     = "Standard_ZRS"
  nullable    = false
  validation {
    condition     = contains(["Standard_LRS", "Standard_ZRS", "Standard_GZRS"], var.sku)
    error_message = "sku must be Standard_LRS, Standard_ZRS or Standard_GZRS."
  }
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.sku != "Standard_LRS"
    error_message = "Staging and production require zone-redundant state: sku Standard_ZRS or Standard_GZRS."
  }
}

variable "private_endpoint" {
  type = object({
    subnet_id           = string
    private_dns_zone_id = string
  })
  description = "Optional existing subnet and privatelink.blob.core.windows.net zone; supplying it disables public network access."
  default     = null
  validation {
    # || does not short-circuit, hence try(); IDs match the exact ARM shape and casing.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+/subnets/[^/]+$", try(var.private_endpoint.subnet_id, ""))) &&
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/privatelink\\.blob\\.core\\.windows\\.net$", try(var.private_endpoint.private_dns_zone_id, "")))
    )
    error_message = "privateEndpoint needs a subnet ARM ID and a privatelink.blob.core.windows.net private DNS zone ARM ID."
  }
}

variable "allowed_ip_ranges" {
  type        = list(string)
  description = "Public IPv4 addresses or CIDR ranges the firewall allows when there is no private_endpoint; empty denies all public clients. Storage rejects /31 and /32: pass a bare address."
  default     = []
  nullable    = false
  validation {
    condition     = var.private_endpoint == null || length(var.allowed_ip_ranges) == 0
    error_message = "allowedIpRanges is only for an account without privateEndpoint, which disables public network access."
  }
  validation {
    condition     = alltrue([for value in var.allowed_ip_ranges : can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}(/[0-9]{1,2})?$", value))])
    error_message = "allowedIpRanges must hold IPv4 addresses or CIDR ranges, such as 203.0.113.0/24."
  }
}
