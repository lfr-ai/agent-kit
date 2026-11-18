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
  description = "Azure region name, for example westeurope; also names the Container Apps private DNS zone."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "name" {
  type        = string
  description = "Virtual network name; also prefixes its NSGs and names the DNS zone links."
  nullable    = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}[a-zA-Z0-9_]$", var.name))
    error_message = "name must be 2-64 letters, digits, underscores, periods or hyphens, starting with a letter or digit and ending with a letter, digit or underscore."
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

variable "address_prefix" {
  type        = string
  description = "One IPv4 network CIDR from /16 to /24. Apps get the first half, private endpoints the third quarter; the last quarter stays free."
  nullable    = false
  validation {
    # The regex rejects IPv6 and malformed lengths; the named bounds limit the length;
    # cidrhost() rejects bad octets and host addresses.
    condition = alltrue([
      can(regex("^(\\d{1,3}\\.){3}\\d{1,3}/\\d{1,2}$", var.address_prefix)),
      try(tonumber(split("/", var.address_prefix)[1]) >= local.min_prefix_length && tonumber(split("/", var.address_prefix)[1]) <= local.max_prefix_length, false),
      try(cidrhost(var.address_prefix, 0) == split("/", var.address_prefix)[0], false),
    ])
    error_message = "addressPrefix must be one IPv4 network address in CIDR notation from /16 to /24, for example 10.20.0.0/22."
  }
}

# VNet prefix-length bounds. A /16 is the largest network this layout splits; a /24
# still leaves Container Apps a /25, above its /27 minimum.
locals {
  min_prefix_length = 16
  max_prefix_length = 24
}

# Kept beside the variables so the key validation and main.tf share one zone list.
# Azure public-cloud zone names from the Private Link DNS reference.
locals {
  zone_names = {
    keyVault          = "privatelink.vaultcore.azure.net"
    redis             = "privatelink.redis.azure.net"
    postgresql        = "privatelink.postgres.database.azure.com"
    blob              = "privatelink.blob.core.windows.net"
    queue             = "privatelink.queue.core.windows.net"
    table             = "privatelink.table.core.windows.net"
    file              = "privatelink.file.core.windows.net"
    dfs               = "privatelink.dfs.core.windows.net"
    containerRegistry = "privatelink.azurecr.io"
    search            = "privatelink.search.windows.net"
    cognitiveServices = "privatelink.cognitiveservices.azure.com"
    openai            = "privatelink.openai.azure.com"
    aiServices        = "privatelink.services.ai.azure.com"
    cosmosDb          = "privatelink.documents.azure.com"
    # Same normalization as the container-apps guard: West Europe -> westeurope.
    containerApps = "privatelink.${lower(replace(var.location, " ", ""))}.azurecontainerapps.io"
    # Azure Monitor Private Link Scope; it also needs the blob zone.
    monitor  = "privatelink.monitor.azure.com"
    oms      = "privatelink.oms.opinsights.azure.com"
    ods      = "privatelink.ods.opinsights.azure.com"
    agentsvc = "privatelink.agentsvc.azure-automation.net"
  }
}

variable "private_dns_zones" {
  type        = list(string)
  description = "Service keys whose private DNS zones are created and linked to this VNet. Default none: a platform-owned hub usually owns them."
  default     = []
  nullable    = false
  validation {
    condition     = alltrue([for key in var.private_dns_zones : contains(keys(local.zone_names), key)])
    error_message = "privateDnsZones accepts only the service keys of the documented zone table."
  }
  validation {
    condition     = length(distinct(var.private_dns_zones)) == length(var.private_dns_zones)
    error_message = "privateDnsZones must not repeat a service key."
  }
}

variable "egress" {
  type = object({
    mode           = string
    route_table_id = optional(string)
  })
  description = "Apps subnet outbound path: platform, natGateway or routeTable. Default null: natGateway for staging and prod, platform for dev and test."
  default     = null
  validation {
    condition     = var.egress == null || try(contains(["platform", "natGateway", "routeTable"], var.egress.mode), false)
    error_message = "egress.mode must be platform, natGateway or routeTable."
  }
  validation {
    condition     = var.egress == null || try(var.egress.mode == "routeTable" ? can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/routeTables/[^/]+$", var.egress.route_table_id)) : var.egress.route_table_id == null, false)
    error_message = "egress.routeTableId must be a route table ARM ID when mode is routeTable, and omitted otherwise."
  }
}