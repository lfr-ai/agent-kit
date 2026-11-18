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
  description = "Azure region, matching the caller's subnet placement policy."
  nullable    = false
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "An Azure location is required."
  }
}

variable "app_name" {
  type        = string
  description = "Container App name; use a distinct name per stage."
  nullable    = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,30}[a-z0-9]$", var.app_name)) && !strcontains(var.app_name, "--")
    error_message = "Use 2-32 lowercase letters, digits or single hyphens; start with a letter and end alphanumeric."
  }
}

variable "environment_name" {
  type        = string
  description = "Managed environment name; also prefixes the dedicated workspace."
  nullable    = false
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,30}[a-z0-9]$", var.environment_name)) && !strcontains(var.environment_name, "--")
    error_message = "Use 2-32 lowercase letters, digits or single hyphens; start with a letter and end alphanumeric."
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

variable "availability" {
  type = object({
    min_replicas             = number
    max_replicas             = number
    zone_redundant           = bool
    deletion_protection      = bool
    infrastructure_subnet_id = optional(string)
  })
  description = "Required explicit capacity/protection choices. Omitting the subnet (null) is allowed only without zones."
  nullable    = false
  validation {
    condition = (
      var.availability.min_replicas >= 0 &&
      var.availability.min_replicas == floor(var.availability.min_replicas) &&
      var.availability.max_replicas == floor(var.availability.max_replicas) &&
      var.availability.max_replicas >= 1 && var.availability.max_replicas <= 30 &&
      var.availability.min_replicas <= var.availability.max_replicas
    )
    error_message = "Use integer replicas with 0 <= min <= max <= 30 and max >= 1; 30 is the toolkit capacity cap."
  }
  validation {
    condition = (
      var.availability.infrastructure_subnet_id == null ? !var.availability.zone_redundant :
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/virtualNetworks/[^/]+/subnets/[^/]+$", var.availability.infrastructure_subnet_id))
    )
    error_message = "Supply a subnet ARM ID; omitting the subnet is allowed only without zone redundancy."
  }
  validation {
    # Staging is prod-like for resilience; deletion protection stays production-only.
    condition     = !contains(["staging", "prod"], var.stage) || (var.availability.zone_redundant && var.availability.min_replicas >= 2)
    error_message = "Toolkit staging and production policy requires zones and min_replicas >= 2."
  }
  validation {
    condition     = var.stage != "prod" || var.availability.deletion_protection
    error_message = "Toolkit production policy requires deletion_protection."
  }
  validation {
    # Kept here, not on internal_environment: an invalid availability would make that
    # flag unknown and silently skip the production private-endpoint check.
    condition     = !var.internal_environment || var.availability.infrastructure_subnet_id != null
    error_message = "internal_environment requires an infrastructure subnet."
  }
}

variable "container_image" {
  type        = string
  description = "Immutable image reference. No tag-only images or image default."
  nullable    = false
  validation {
    condition     = can(regex("^[A-Za-z0-9._:/-]+/[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$", var.container_image))
    error_message = "Use registry/repository@sha256: followed by 64 lowercase hex digits."
  }
}

variable "target_port" {
  type        = number
  description = "Application HTTP port; ingress terminates TLS."
  default     = 8080
  nullable    = false
  validation {
    condition     = var.target_port >= 1 && var.target_port <= 65535 && var.target_port == floor(var.target_port)
    error_message = "target_port must be an integer from 1 to 65535."
  }
}

variable "cpu" {
  type        = number
  description = "vCPU per replica, from 0.25 to 4 in 0.25 steps (Consumption workload profile)."
  default     = 0.5
  nullable    = false
  validation {
    condition     = contains(keys(local.resource_pairs), tostring(var.cpu))
    error_message = "cpu must be 0.25 to 4 in 0.25 steps."
  }
}

variable "memory" {
  type        = string
  description = "Memory per replica; must be twice the cpu in Gi, such as 1Gi for 0.5."
  default     = "1Gi"
  nullable    = false
  validation {
    # An invalid cpu is reported by its own variable only.
    condition     = !contains(keys(local.resource_pairs), tostring(var.cpu)) || local.resource_pairs[tostring(var.cpu)] == var.memory
    error_message = "cpu and memory must be a Consumption pair: cpu 0.25 to 4 in 0.25 steps with memory twice the cpu in Gi, such as 0.5 and 1Gi."
  }
}

# Consumption workload profile: always twice as many GiB as vCPU.
locals {
  resource_pairs = {
    "0.25" = "0.5Gi", "0.5" = "1Gi", "0.75" = "1.5Gi", "1" = "2Gi",
    "1.25" = "2.5Gi", "1.5" = "3Gi", "1.75" = "3.5Gi", "2" = "4Gi",
    "2.25" = "4.5Gi", "2.5" = "5Gi", "2.75" = "5.5Gi", "3" = "6Gi",
    "3.25" = "6.5Gi", "3.5" = "7Gi", "3.75" = "7.5Gi", "4" = "8Gi",
  }
}

variable "existing_log_analytics_workspace_resource_id" {
  type        = string
  description = "Caller-owned Log Analytics workspace ARM ID. Omit (null) to create the dedicated workspace; supplied IDs are never managed or locked."
  default     = null
  validation {
    condition = var.existing_log_analytics_workspace_resource_id == null ? true : (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.OperationalInsights/workspaces/[^/]+$", var.existing_log_analytics_workspace_resource_id)) &&
      !can(regex("[[:space:]\\p{Z}\\x{0085}]", var.existing_log_analytics_workspace_resource_id))
    )
    error_message = "existingLogAnalyticsWorkspaceResourceId must be omitted or a full Microsoft.OperationalInsights/workspaces ARM ID without whitespace."
  }
}

variable "log_retention_days" {
  type        = number
  description = "Log Analytics retention in days for the dedicated workspace."
  default     = 30
  nullable    = false
  validation {
    condition     = var.log_retention_days >= 30 && var.log_retention_days <= 730 && var.log_retention_days == floor(var.log_retention_days)
    error_message = "log_retention_days must be an integer from 30 to 730."
  }
}

variable "existing_identity_resource_id" {
  type        = string
  description = "Pre-authorized user-assigned identity. Omit (null) to create a dedicated identity."
  default     = null
  validation {
    condition     = var.existing_identity_resource_id == null ? true : can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.ManagedIdentity/userAssignedIdentities/[^/]+$", var.existing_identity_resource_id))
    error_message = "Supply a user-assigned managed identity ARM ID, or omit it."
  }
}

variable "registry_server" {
  type        = string
  description = "Optional ACR login server (no scheme); identity pull authorization is operator-owned."
  default     = null
  validation {
    condition     = var.registry_server == null ? true : can(regex("^[a-z0-9.-]+\\.azurecr\\.io$", var.registry_server))
    error_message = "registry_server must be an azurecr.io login server without a scheme, or omitted."
  }
  validation {
    condition     = var.registry_server == null ? true : startswith(var.container_image, "${var.registry_server}/")
    error_message = "container_image must come from registry_server when it is set."
  }
  validation {
    condition     = var.registry_server == null || var.existing_identity_resource_id != null
    error_message = "Private ACR access requires an existing pre-authorized user-assigned identity."
  }
}

variable "secret_references" {
  type = list(object({
    name                 = string
    environment_variable = string
    key_vault_url        = string
  }))
  description = "Key Vault references only, never values. Azure public cloud secret URLs."
  default     = []
  nullable    = false
  validation {
    condition     = length(var.secret_references) == 0 || var.existing_identity_resource_id != null
    error_message = "Key Vault references require an existing pre-authorized user-assigned identity."
  }
  validation {
    condition = (
      length(distinct(var.secret_references[*].name)) == length(var.secret_references) &&
      alltrue([for ref in var.secret_references :
        can(regex("^[a-z0-9][a-z0-9-]{0,252}$", ref.name))
      ])
    )
    error_message = "Secret names must be unique: use 1-253 lowercase letters, digits or hyphens, starting alphanumeric."
  }
  validation {
    condition = (
      length(distinct([for ref in var.secret_references : upper(ref.environment_variable)])) == length(var.secret_references) &&
      alltrue([for ref in var.secret_references :
        can(regex("^[A-Za-z_][A-Za-z0-9_]*$", ref.environment_variable))
      ])
    )
    error_message = "Environment variable names must be unique ignoring case and match [A-Za-z_][A-Za-z0-9_]*."
  }
  validation {
    condition = alltrue([for ref in var.secret_references :
      can(regex("^https://[a-zA-Z0-9-]+\\.vault\\.azure\\.net/secrets/[a-zA-Z0-9-]+(/[a-fA-F0-9]{32})?$", ref.key_vault_url))
    ])
    error_message = "Use HTTPS Azure public-cloud Key Vault secret URLs, with an optional 32-hex version."
  }
  validation {
    condition = (
      length(setintersection([for ref in var.secret_references : upper(ref.environment_variable)], local.reserved_environment_names)) == 0
    )
    error_message = "secret_references must not set reserved telemetry or credential-override names in any casing; OTEL_EXPORTER_OTLP_HEADERS is expected."
  }
}

# Always reserved, ignoring case: telemetry names, so enabling telemetry cannot introduce
# duplicates, and the Azure Identity credential overrides, which would make
# DefaultAzureCredential pick a client secret, certificate or federated token before the
# managed identity.
locals {
  reserved_environment_names = [
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "AZURE_CLIENT_ID",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "AZURE_CLIENT_SECRET",
    "AZURE_CLIENT_CERTIFICATE_PATH",
    "AZURE_FEDERATED_TOKEN_FILE",
  ]
}

variable "environment_variables" {
  type        = map(string)
  description = "Nonsecret environment values only; credentials belong in secret_references."
  default     = {}
  nullable    = false
  validation {
    condition = (
      length(distinct([for name in keys(var.environment_variables) : upper(name)])) == length(var.environment_variables) &&
      alltrue([for name, value in var.environment_variables :
        can(regex("^[A-Za-z_][A-Za-z0-9_]*$", name)) && value != null
      ])
    )
    error_message = "environment_variables needs valid names unique ignoring case and non-null string values."
  }
  validation {
    condition = length(setintersection(
      [for name in keys(var.environment_variables) : upper(name)],
      [for ref in var.secret_references : upper(ref.environment_variable)]
    )) == 0
    error_message = "environment_variables and secret_references must not set the same environment name, ignoring case."
  }
  validation {
    condition = length(setintersection([for name in keys(var.environment_variables) : upper(name)], concat(local.reserved_environment_names, [
      "APP_POSTGRES_PASSWORD", "APP_REDIS_URL", "APP_AI_API_KEY", "OTEL_EXPORTER_OTLP_HEADERS",
    ]))) == 0
    error_message = "environment_variables must not set reserved telemetry or credential-override names or credential slots in any casing; use Key Vault references for credentials."
  }
}

variable "application_insights_connection_string" {
  type        = string
  description = "Optional Application Insights connection string, such as the application-insights output. Needs an existing identity granted Monitoring Metrics Publisher."
  default     = null
  validation {
    condition     = var.application_insights_connection_string == null ? true : strcontains(var.application_insights_connection_string, "InstrumentationKey=")
    error_message = "application_insights_connection_string needs InstrumentationKey=, or must be omitted."
  }
  validation {
    condition     = var.application_insights_connection_string == null || var.existing_identity_resource_id != null
    error_message = "Application Insights telemetry requires an existing pre-authorized user-assigned identity."
  }
}

variable "otlp_endpoint" {
  type        = string
  description = "Optional https:// OTLP/HTTP base URL, such as Langfuse. Pass its headers as a secret_references entry for OTEL_EXPORTER_OTLP_HEADERS."
  default     = null
  validation {
    condition     = var.otlp_endpoint == null ? true : startswith(lower(var.otlp_endpoint), "https://")
    error_message = "otlp_endpoint needs https://, or must be omitted."
  }
}

variable "internal_environment" {
  type        = bool
  description = "Internal load balancer for VNet clients; app ingress stays external=true."
  default     = false
  nullable    = false
}

variable "linked_virtual_network_ids" {
  type        = list(string)
  description = "Extra VNet ARM IDs, such as a hub or peered VNets, linked to the internal environment DNS zone. Requires internal_environment."
  default     = []
  nullable    = false
  validation {
    condition = length(var.linked_virtual_network_ids) == 0 || (
      var.internal_environment &&
      alltrue([for id in var.linked_virtual_network_ids : can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/virtualNetworks/[^/]+$", id))]) &&
      length(distinct([for id in var.linked_virtual_network_ids : lower(id)])) == length(var.linked_virtual_network_ids) &&
      (var.availability.infrastructure_subnet_id == null ? true : !contains([for id in var.linked_virtual_network_ids : lower(id)], lower(join("/", slice(split("/", var.availability.infrastructure_subnet_id), 0, min(9, length(split("/", var.availability.infrastructure_subnet_id))))))))
    )
    error_message = "linkedVirtualNetworkIds requires internalEnvironment and unique virtual network ARM IDs other than the infrastructure VNet."
  }
}

variable "public_network_access" {
  type        = string
  description = "Explicit environment public reachability; omit (null) to preserve the platform/previous setting. Internal environments and private endpoints always disable it."
  default     = null
  validation {
    condition     = var.public_network_access == null ? true : contains(["Enabled", "Disabled"], var.public_network_access)
    error_message = "public_network_access must be omitted, Enabled or Disabled."
  }
  validation {
    # Internal environments and private endpoints accept only Disabled.
    condition     = var.public_network_access != "Enabled" || (!var.internal_environment && var.private_endpoint == null)
    error_message = "public_network_access Enabled cannot be combined with internal_environment or private_endpoint; both require Disabled."
  }
}

variable "private_endpoint" {
  type = object({
    subnet_id           = string
    private_dns_zone_id = string
  })
  description = "Separate Private Link topology. Staging and prod require this or an internal environment, never both."
  default     = null
  validation {
    condition     = !contains(["staging", "prod"], var.stage) || var.private_endpoint != null || var.internal_environment
    error_message = "Staging and prod require private_endpoint or an internal environment."
  }
  validation {
    condition     = var.private_endpoint == null || !var.internal_environment
    error_message = "internal_environment cannot be combined with private_endpoint."
  }
  validation {
    # can()/try() turn attribute access on null into false; the null case is allowed explicitly.
    # The zone name embeds the region name, for example privatelink.westeurope.azurecontainerapps.io.
    condition = var.private_endpoint == null || (
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/virtualNetworks/[^/]+/subnets/[^/]+$", var.private_endpoint.subnet_id)) &&
      can(regex("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\\.Network/privateDnsZones/[^/]+$", var.private_endpoint.private_dns_zone_id)) &&
      endswith(try(var.private_endpoint.private_dns_zone_id, ""), "/privatelink.${lower(replace(var.location, " ", ""))}.azurecontainerapps.io")
    )
    error_message = "privateEndpoint needs a subnet ARM ID and the private DNS zone ARM ID of privatelink.<location>.azurecontainerapps.io for this location."
  }
}

variable "authentication" {
  type = object({
    client_id         = string
    tenant_id         = string
    sign_in           = optional(bool, false)
    allowed_audiences = optional(list(string))
    public_host_name  = optional(string)
    excluded_paths    = optional(list(string))
  })
  description = "Optional Microsoft Entra built-in authentication. sign_in false: API mode, bearer tokens only, 401 without one; true: browser sign-in with ID tokens, no client secret. public_host_name is the public host of an operator-owned edge or the custom-domain host. excluded_paths are served without authentication, such as /health/ready. Authorization by roles or groups stays in the app, using token claims."
  default     = null
  validation {
    # can() turns attribute access on null into false; the null case is allowed explicitly.
    condition = var.authentication == null || (
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.authentication.client_id)) &&
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.authentication.tenant_id)) &&
      (try(var.authentication.public_host_name, null) == null ? true : (length(var.authentication.public_host_name) <= 253 && can(regex("^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.authentication.public_host_name)))) &&
      alltrue([for path in coalesce(try(var.authentication.excluded_paths, null), []) : can(regex("^/[^[:space:]]*$", path))])
    )
    error_message = "authentication needs GUID client_id and tenant_id, public_host_name as a lowercase host name without scheme or path, and excluded_paths starting with /."
  }
}

variable "custom_domain" {
  type = object({
    host_name        = string
    bind_certificate = optional(bool, false)
  })
  description = "Optional public subdomain with a free managed certificate. Apply with bind_certificate false first, then true."
  default     = null
  validation {
    # can() turns attribute access on null into false; the null case is allowed explicitly.
    condition = var.custom_domain == null || (
      length(try(var.custom_domain.host_name, "")) <= 253 &&
      can(regex("^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.){2,}[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.custom_domain.host_name)) &&
      !var.internal_environment && var.private_endpoint == null && var.public_network_access != "Disabled"
    )
    error_message = "customDomain needs a lowercase subdomain host name on a public environment: no internalEnvironment, privateEndpoint or publicNetworkAccess Disabled."
  }
}
