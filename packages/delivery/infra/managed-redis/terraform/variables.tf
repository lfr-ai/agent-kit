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
  description = "Azure region for the cache and its optional private endpoint."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Cache name; also prefixes the private endpoint. Use a distinct name per stage."
  nullable    = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,30}[a-z0-9]$", var.name)) && !strcontains(var.name, "--")
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

variable "principal_id" {
  type        = string
  description = "Object (principal) ID of the existing app managed identity that receives data access."
  nullable    = false
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.principal_id))
    error_message = "principalId must be the object (principal) ID GUID of the existing app identity."
  }
}

variable "sku" {
  type        = string
  description = "Azure Managed Redis SKU. Production rejects Balanced_B0 and Balanced_B1."
  default     = "Balanced_B0"
  nullable    = false
  validation {
    condition     = can(regex("^(Balanced_B|MemoryOptimized_M|ComputeOptimized_X|FlashOptimized_A)[0-9]+$", var.sku))
    error_message = "sku must be an Azure Managed Redis SKU, for example Balanced_B0 or MemoryOptimized_M10."
  }
  validation {
    condition     = var.stage != "prod" || !contains(["Balanced_B0", "Balanced_B1"], var.sku)
    error_message = "Production rejects the dev/test sizes Balanced_B0 and Balanced_B1; choose Balanced_B3 or larger."
  }
}

variable "private_endpoint" {
  type = object({
    subnet_id           = string
    private_dns_zone_id = string
  })
  description = "Existing subnet and privatelink.redis.azure.net zone; required in staging and production. Public network access is disabled unless allow_public_network_access is set."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.private_endpoint != null
    error_message = "Staging and production require privateEndpoint: an existing subnet and privatelink.redis.azure.net zone."
  }
  validation {
    # can() turns attribute access on null into false; the null case is allowed explicitly.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+/subnets/[^/]+$", var.private_endpoint.subnet_id)) &&
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/privatelink\\.redis\\.azure\\.net$", var.private_endpoint.private_dns_zone_id))
    )
    error_message = "privateEndpoint needs a subnet ARM ID and a privatelink.redis.azure.net private DNS zone ARM ID."
  }
}

variable "allow_public_network_access" {
  type        = bool
  description = "Dev or test without private_endpoint only: keep the public endpoint. Azure Managed Redis has no IP firewall; Entra ID still guards data access."
  default     = false
  nullable    = false
  validation {
    condition     = !var.allow_public_network_access || (var.private_endpoint == null && !contains(["staging", "prod"], var.stage))
    error_message = "allowPublicNetworkAccess is only for dev or test without privateEndpoint."
  }
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "Existing Log Analytics workspace ARM ID for metrics and connection logs; required in staging and production."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.log_analytics_workspace_id != null
    error_message = "Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for diagnostics."
  }
  validation {
    condition     = var.log_analytics_workspace_id == null || can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.OperationalInsights/workspaces/[^/]+$", var.log_analytics_workspace_id))
    error_message = "logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID."
  }
}
