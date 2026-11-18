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
  description = "Azure region for the server and its optional private endpoint."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Globally unique server name; also prefixes the private endpoint. Use a distinct name per stage."
  nullable    = false
  validation {
    condition     = length(var.name) >= 3 && length(var.name) <= 63
    error_message = "name must be 3-63 characters."
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

variable "administrator" {
  type = object({
    object_id = string
    name      = string
    type      = string
  })
  description = "Existing Entra principal that administers the server and creates database roles; name is its display name."
  nullable    = false
  validation {
    condition     = length(var.administrator.object_id) == 36
    error_message = "administrator.objectId must be a 36-character object (principal) ID."
  }
  validation {
    condition     = length(var.administrator.name) > 0
    error_message = "administrator.name must be the principal's Entra display name."
  }
  validation {
    condition     = contains(["User", "Group", "ServicePrincipal"], var.administrator.type)
    error_message = "administrator.type must be User, Group or ServicePrincipal."
  }
}

variable "database_name" {
  type        = string
  description = "Application database created on the server."
  nullable    = false
  validation {
    condition     = length(var.database_name) >= 1 && length(var.database_name) <= 63
    error_message = "databaseName must be 1-63 characters."
  }
}

variable "sku" {
  type = object({
    name = string
    tier = string
  })
  description = "Compute size; defaults to Standard_B1ms (Burstable) in dev/test and Standard_D2ds_v5 (GeneralPurpose) in production."
  default     = null
  validation {
    condition     = var.sku == null ? true : contains(["Burstable", "GeneralPurpose", "MemoryOptimized"], var.sku.tier)
    error_message = "sku.tier must be Burstable, GeneralPurpose or MemoryOptimized."
  }
  validation {
    condition     = var.sku == null ? true : var.stage != "prod" || var.sku.tier != "Burstable"
    error_message = "Production needs a GeneralPurpose or MemoryOptimized sku; Burstable has no zone-redundant high availability."
  }
}

variable "storage_size_gb" {
  type        = number
  description = "Initial Premium SSD storage in GiB; 32 is the smallest size. Autogrow raises it online, and storage can never shrink."
  default     = 32
  nullable    = false
  validation {
    condition     = var.storage_size_gb >= 32 && floor(var.storage_size_gb) == var.storage_size_gb
    error_message = "storageSizeGB must be a whole number of at least 32 GiB."
  }
}

variable "private_endpoint" {
  type = object({
    subnet_id           = string
    private_dns_zone_id = string
  })
  description = "Existing subnet and privatelink.postgres.database.azure.com zone; required in staging and production."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.private_endpoint != null
    error_message = "Staging and production require privateEndpoint: an existing subnet and privatelink.postgres.database.azure.com zone."
  }
  validation {
    # || does not short-circuit, hence try(); IDs match the exact ARM shape and casing.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+/subnets/[^/]+$", try(var.private_endpoint.subnet_id, ""))) &&
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/privatelink\\.postgres\\.database\\.azure\\.com$", try(var.private_endpoint.private_dns_zone_id, "")))
    )
    error_message = "privateEndpoint needs a subnet ARM ID and a privatelink.postgres.database.azure.com private DNS zone ARM ID."
  }
}

variable "allow_public_network_access" {
  type        = bool
  description = "Dev or test without private_endpoint only: keep the public endpoint, with firewall rules for allowed_ip_ranges only."
  default     = false
  nullable    = false
  validation {
    condition     = !var.allow_public_network_access || (var.private_endpoint == null && !contains(["staging", "prod"], var.stage))
    error_message = "allowPublicNetworkAccess is only for dev or test without privateEndpoint."
  }
}

variable "allowed_ip_ranges" {
  type        = list(string)
  description = "IPv4 addresses or CIDR ranges that get a firewall rule with allow_public_network_access."
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
  description = "Existing Log Analytics workspace ARM ID for server logs and metrics; required in staging and production."
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

variable "extensions" {
  type        = list(string)
  description = "Extensions to allowlist in azure.extensions, for example vector or age; empty allows none."
  default     = []
  nullable    = false
}
