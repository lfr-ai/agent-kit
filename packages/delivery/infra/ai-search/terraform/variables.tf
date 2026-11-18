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
  description = "Azure region for the search service and its optional private endpoint."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Globally unique search service name; also prefixes the private endpoint. Use a distinct name per stage."
  nullable    = false
  validation {
    condition     = length(var.name) >= 2 && length(var.name) <= 60
    error_message = "name must be 2-60 characters."
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
  description = "Object (principal) ID of the existing app identity that queries indexes, not its client ID."
  nullable    = false
  validation {
    condition     = length(var.principal_id) == 36
    error_message = "principalId must be a 36-character object (principal) ID."
  }
}

variable "indexing_principal_id" {
  type        = string
  description = "Optional object (principal) ID of an existing workload identity that loads documents into indexes."
  default     = null
  validation {
    condition     = var.indexing_principal_id == null ? true : length(var.indexing_principal_id) == 36
    error_message = "indexingPrincipalId must be a 36-character object (principal) ID."
  }
}

# Beside the variables because validations cannot read main.tf-only locals in the
# variable contract test. The production replica floor for the read SLA; also the
# production default.
locals {
  production_min_replicas = 2
}

variable "replica_count" {
  type        = number
  description = "Replicas; production defaults to 2 for the read SLA. Use 3 for read-write; Basic allows at most 3."
  default     = null
  validation {
    condition     = var.replica_count == null ? true : var.replica_count >= 1 && var.replica_count <= 12
    error_message = "replicaCount must be 1-12."
  }
  validation {
    condition     = var.replica_count == null ? true : var.stage != "prod" || var.replica_count >= local.production_min_replicas
    error_message = "Production needs replicaCount 2 or more for the read SLA; use 3 for read-write."
  }
}

variable "private_endpoint" {
  type = object({
    subnet_id           = string
    private_dns_zone_id = string
  })
  description = "Existing subnet and privatelink.search.windows.net zone; required in staging and production."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.private_endpoint != null
    error_message = "Staging and production require privateEndpoint: an existing subnet and privatelink.search.windows.net zone."
  }
  validation {
    # || does not short-circuit, hence try(); IDs match the exact ARM shape and casing.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/virtualNetworks/[^/]+/subnets/[^/]+$", try(var.private_endpoint.subnet_id, ""))) &&
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/privatelink\\.search\\.windows\\.net$", try(var.private_endpoint.private_dns_zone_id, "")))
    )
    error_message = "privateEndpoint needs a subnet ARM ID and a privatelink.search.windows.net private DNS zone ARM ID."
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
  description = "IPv4 addresses or CIDR ranges the search firewall allows; at least one is needed with allow_public_network_access."
  default     = []
  nullable    = false
  validation {
    condition     = var.allow_public_network_access || length(var.allowed_ip_ranges) == 0
    error_message = "allowedIpRanges needs allowPublicNetworkAccess."
  }
  validation {
    # Azure AI Search treats an empty IP rule list as open to all networks.
    condition     = !var.allow_public_network_access || length(var.allowed_ip_ranges) > 0
    error_message = "allowPublicNetworkAccess needs allowedIpRanges: Azure AI Search treats an empty list as all networks."
  }
  validation {
    condition     = alltrue([for value in var.allowed_ip_ranges : can(regex("^[0-9]{1,3}(\\.[0-9]{1,3}){3}(/[0-9]{1,2})?$", value))])
    error_message = "allowedIpRanges must hold IPv4 addresses or CIDR ranges, such as 203.0.113.0/24."
  }
}

variable "log_analytics_workspace_id" {
  type        = string
  description = "Existing Log Analytics workspace ARM ID for operation logs and metrics; required in staging and production."
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
