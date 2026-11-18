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
  description = "Azure region for the account and its optional private endpoint."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Globally unique account name: lowercase letters, digits and hyphens; also prefixes the private endpoint. Use a distinct name per stage."
  nullable    = false
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,43}$", var.name))
    error_message = "name must be 3-44 lowercase letters, digits or hyphens, starting with a letter or digit."
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

variable "database" {
  type = object({
    name = string
    containers = optional(list(object({
      name               = string
      partition_key_path = string
    })), [])
  })
  description = "Optional NoSQL database and its containers; null creates neither. Partition key paths cannot change after creation."
  default     = null
  validation {
    condition     = var.database == null || try(length(var.database.name) >= 1 && length(var.database.name) <= 255, false)
    error_message = "database.name must be 1-255 characters."
  }
  validation {
    condition = var.database == null || try(alltrue([
      for container in var.database.containers :
      length(container.name) >= 1 && length(container.name) <= 255 && can(regex("^/[^/]", container.partition_key_path))
    ]), false)
    error_message = "Each container needs a 1-255 character name and a partition key path such as /tenantId."
  }
  validation {
    condition     = var.database == null || try(length(var.database.containers) == length(distinct([for container in var.database.containers : container.name])), false)
    error_message = "Container names must be unique."
  }
}

variable "autoscale_max_throughput" {
  type        = number
  description = "Production autoscale maximum RU/s shared by the database; serverless dev/test accounts ignore it."
  default     = 1000
  nullable    = false
  validation {
    condition     = var.autoscale_max_throughput >= 1000
    error_message = "autoscaleMaxThroughput must be at least 1000 RU/s."
  }
}

variable "principal_id" {
  type        = string
  description = "Object (principal) ID of an existing identity to get Cosmos DB Built-in Data Contributor on the account, not its client ID; null grants nobody."
  default     = null
  validation {
    condition     = var.principal_id == null || try(length(var.principal_id) == 36, false)
    error_message = "principalId must be a 36-character object (principal) ID."
  }
}

variable "private_endpoint" {
  type = object({
    subnet_id           = string
    private_dns_zone_id = string
  })
  description = "Existing subnet and privatelink.documents.azure.com zone; required in staging and production. Public network access is disabled unless allow_public_network_access is set."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.private_endpoint != null
    error_message = "Staging and production require privateEndpoint: an existing subnet and privatelink.documents.azure.com zone."
  }
  validation {
    # can() turns attribute access on null into false; the null case is allowed explicitly.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+/subnets/[^/]+$", var.private_endpoint.subnet_id)) &&
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/privatelink\\.documents\\.azure\\.com$", var.private_endpoint.private_dns_zone_id))
    )
    error_message = "privateEndpoint needs a subnet ARM ID and a privatelink.documents.azure.com private DNS zone ARM ID."
  }
}

variable "allow_public_network_access" {
  type        = bool
  description = "Dev or test without private_endpoint only: keep the public endpoint, allowing only allowed_ip_ranges."
  default     = false
  nullable    = false
  validation {
    condition     = !var.allow_public_network_access || (var.private_endpoint == null && !contains(["staging", "prod"], var.stage))
    error_message = "allowPublicNetworkAccess is only for dev or test without privateEndpoint."
  }
}

variable "allowed_ip_ranges" {
  type        = list(string)
  description = "IPv4 addresses or CIDR ranges the firewall allows; at least one is needed with allow_public_network_access."
  default     = []
  nullable    = false
  validation {
    condition     = var.allow_public_network_access || length(var.allowed_ip_ranges) == 0
    error_message = "allowedIpRanges needs allowPublicNetworkAccess."
  }
  validation {
    # Cosmos DB treats an empty IP rule list as open to all networks.
    condition     = !var.allow_public_network_access || length(var.allowed_ip_ranges) > 0
    error_message = "allowPublicNetworkAccess needs allowedIpRanges: Cosmos DB treats an empty list as all networks."
  }
  validation {
    condition     = alltrue([for value in var.allowed_ip_ranges : can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}(/[0-9]{1,2})?$", value))])
    error_message = "allowedIpRanges must hold IPv4 addresses or CIDR ranges, such as 203.0.113.0/24."
  }
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "Existing Log Analytics workspace ARM ID for request logs and metrics; required in staging and production."
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
