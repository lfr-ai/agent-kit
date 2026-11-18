locals {
  tags         = { stage = var.stage }
  identity_id  = var.existing_identity_resource_id == null ? azapi_resource.identity[0].id : var.existing_identity_resource_id
  workspace_id = var.existing_log_analytics_workspace_resource_id == null ? azapi_resource.workspace[0].id : var.existing_log_analytics_workspace_resource_id
  auth_sign_in = try(var.authentication.sign_in, false) == true
  auth_host    = try(var.authentication.public_host_name, null)
  domain_host  = try(var.custom_domain.host_name, null)
  domain_bound = try(var.custom_domain.bind_certificate, false) == true
  # The app refers to the certificate by ID, so the certificate can depend on the app without a cycle.
  certificate_name = "${var.app_name}-cert"
  certificate_id   = "${azapi_resource.environment.id}/managedCertificates/${var.app_name}-cert"
  # Startup allows 30 x 10 s for a cold start; liveness and readiness then poll the health endpoints.
  probe_settings = {
    startup   = { periodSeconds = 10, timeoutSeconds = 2, failureThreshold = 30 }
    liveness  = { initialDelaySeconds = 10, periodSeconds = 10, timeoutSeconds = 2, failureThreshold = 3 }
    readiness = { initialDelaySeconds = 5, periodSeconds = 5, timeoutSeconds = 2, failureThreshold = 3 }
  }
  # Plain values only: the connection string is an identifier, not a credential.
  # OTLP headers are credentials and arrive through secret_references instead.
  telemetry_variables = concat(
    var.application_insights_connection_string == null && var.otlp_endpoint == null ? [] : [
      { name = "OTEL_SERVICE_NAME", value = var.app_name },
      { name = "OTEL_RESOURCE_ATTRIBUTES", value = "deployment.environment.name=${var.stage}" },
    ],
    var.application_insights_connection_string == null ? [] : [
      { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = var.application_insights_connection_string },
      # Selects the user-assigned identity for Entra ID authenticated ingestion.
      { name = "AZURE_CLIENT_ID", value = data.azapi_resource.identity[0].output.properties.clientId },
    ],
    var.otlp_endpoint == null ? [] : [
      { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = var.otlp_endpoint },
      # OpenTelemetry SDKs may default to gRPC; Langfuse accepts OTLP over HTTP only.
      { name = "OTEL_EXPORTER_OTLP_PROTOCOL", value = "http/protobuf" },
    ],
  )
}

# Reads only the client ID of the caller's identity. The count does not depend on
# the connection string, which may be unknown until a sibling module is applied.
data "azapi_resource" "identity" {
  count                  = var.existing_identity_resource_id == null ? 0 : 1
  type                   = "Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30"
  resource_id            = var.existing_identity_resource_id
  response_export_values = ["properties.clientId"]
}

resource "azapi_resource" "identity" {
  count                  = var.existing_identity_resource_id == null ? 1 : 0
  type                   = "Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30"
  name                   = "${var.app_name}-identity"
  parent_id              = var.resource_group_id
  location               = var.location
  tags                   = local.tags
  body                   = {}
  response_export_values = []
}

// Preserve existing dedicated-workspace state when adding optional reuse.
moved {
  from = azapi_resource.workspace
  to   = azapi_resource.workspace[0]
}

resource "azapi_resource" "workspace" {
  count     = var.existing_log_analytics_workspace_resource_id == null ? 1 : 0
  type      = "Microsoft.OperationalInsights/workspaces@2025-07-01"
  name      = "${var.environment_name}-logs"
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    properties = {
      sku             = { name = "PerGB2018" }
      retentionInDays = var.log_retention_days
      features = {
        disableLocalAuth                            = true
        enableLogAccessUsingOnlyResourcePermissions = true
      }
    }
  }
  response_export_values = []
}

resource "azapi_resource" "environment" {
  type      = "Microsoft.App/managedEnvironments@2025-07-01"
  name      = var.environment_name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    properties = merge({
      appLogsConfiguration = { destination = "azure-monitor" }
      zoneRedundant        = var.availability.zone_redundant
      workloadProfiles     = [{ name = "Consumption", workloadProfileType = "Consumption" }]
      }, var.availability.infrastructure_subnet_id == null ? {} : {
      # App ingress remains external=true for clients elsewhere in the VNet.
      vnetConfiguration = {
        infrastructureSubnetId = var.availability.infrastructure_subnet_id
        internal               = var.internal_environment
      }
      }, var.internal_environment || var.private_endpoint != null ? { publicNetworkAccess = "Disabled" } :
    var.public_network_access == null ? {} : { publicNetworkAccess = var.public_network_access })
  }
  response_export_values = ["properties.defaultDomain", "properties.staticIp", "properties.customDomainConfiguration.customDomainVerificationId"]
}

# Internal environments use their default domain, not the Private Link zone.
resource "azapi_resource" "internal_dns" {
  count                  = var.internal_environment ? 1 : 0
  type                   = "Microsoft.Network/privateDnsZones@2024-06-01"
  name                   = azapi_resource.environment.output.properties.defaultDomain
  parent_id              = var.resource_group_id
  location               = "global"
  tags                   = local.tags
  body                   = {}
  response_export_values = []
}

resource "azapi_resource" "internal_dns_link" {
  count     = var.internal_environment ? 1 : 0
  type      = "Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01"
  name      = var.environment_name
  parent_id = azapi_resource.internal_dns[0].id
  location  = "global"
  body = {
    properties = {
      # Positional: a resource group or VNet literally named "subnets" stays intact.
      virtualNetwork      = { id = join("/", slice(split("/", var.availability.infrastructure_subnet_id), 0, 9)) }
      registrationEnabled = false
    }
  }
  response_export_values = []
}

# Extra links for hub or peered VNets; names match Bicep guid(toLower(id)).
resource "azapi_resource" "internal_dns_extra_links" {
  for_each  = var.internal_environment ? { for id in var.linked_virtual_network_ids : lower(id) => id } : {}
  type      = "Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01"
  name      = "${var.environment_name}-${uuidv5(local.guid_namespace, each.key)}"
  parent_id = azapi_resource.internal_dns[0].id
  location  = "global"
  body = {
    properties = {
      virtualNetwork      = { id = each.value }
      registrationEnabled = false
    }
  }
  response_export_values = []
}

locals {
  # Bicep guid() is a UUIDv5 under this fixed namespace.
  guid_namespace = "11fb06fb-712d-4ddd-98c7-e71bbd588830"
  # Five-minute TTL for the wildcard and apex A records of the environment static IP.
  dns_ttl_seconds = 300
}

resource "azapi_resource" "internal_dns_records" {
  for_each  = var.internal_environment ? toset(["*", "@"]) : toset([])
  type      = "Microsoft.Network/privateDnsZones/A@2024-06-01"
  name      = each.key
  parent_id = azapi_resource.internal_dns[0].id
  body = {
    properties = {
      ttl      = local.dns_ttl_seconds
      aRecords = [{ ipv4Address = azapi_resource.environment.output.properties.staticIp }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "internal_dns_protection" {
  count     = var.internal_environment && var.availability.deletion_protection ? 1 : 0
  type      = "Microsoft.Authorization/locks@2020-05-01"
  name      = "foundation-protection"
  parent_id = azapi_resource.internal_dns[0].id
  # Lock after its children so destroy removes the CanNotDelete lock before them.
  depends_on = [
    azapi_resource.internal_dns_link,
    azapi_resource.internal_dns_extra_links,
    azapi_resource.internal_dns_records,
  ]
  body = {
    properties = { level = "CanNotDelete" }
  }
  response_export_values = []
}

resource "azapi_resource" "endpoint" {
  count     = var.private_endpoint == null ? 0 : 1
  type      = "Microsoft.Network/privateEndpoints@2025-01-01"
  name      = "${var.environment_name}-pe"
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    properties = {
      subnet = { id = var.private_endpoint.subnet_id }
      privateLinkServiceConnections = [{
        name = var.environment_name
        properties = {
          privateLinkServiceId = azapi_resource.environment.id
          groupIds             = ["managedEnvironments"]
        }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "dns_zone_group" {
  count     = length(azapi_resource.endpoint)
  type      = "Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01"
  name      = "default"
  parent_id = azapi_resource.endpoint[0].id
  body = {
    properties = {
      privateDnsZoneConfigs = [{
        name       = "container-apps"
        properties = { privateDnsZoneId = var.private_endpoint.private_dns_zone_id }
      }]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "diagnostics" {
  type      = "Microsoft.Insights/diagnosticSettings@2021-05-01-preview"
  name      = "container-apps-logs"
  parent_id = azapi_resource.environment.id
  body = {
    properties = {
      workspaceId = local.workspace_id
      logs = [
        { category = "ContainerAppConsoleLogs", enabled = true },
        { category = "ContainerAppSystemLogs", enabled = true }
      ]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "app" {
  type      = "Microsoft.App/containerApps@2025-07-01"
  name      = var.app_name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  identity {
    type         = "UserAssigned"
    identity_ids = [local.identity_id]
  }
  body = {
    properties = {
      environmentId       = azapi_resource.environment.id
      workloadProfileName = "Consumption"
      configuration = {
        activeRevisionsMode = "Single"
        ingress = {
          external      = true
          allowInsecure = false
          targetPort    = var.target_port
          transport     = "http"
          # Declarative: removing custom_domain also removes the host name binding.
          customDomains = local.domain_host == null ? [] : [merge(
            { name = local.domain_host, bindingType = local.domain_bound ? "SniEnabled" : "Disabled" },
            local.domain_bound ? { certificateId = local.certificate_id } : {},
          )]
        }
        registries = var.registry_server == null ? [] : [
          { server = var.registry_server, identity = local.identity_id }
        ]
        secrets = [for ref in var.secret_references : {
          name        = ref.name
          keyVaultUrl = ref.key_vault_url
          identity    = local.identity_id
        }]
      }
      template = {
        containers = [{
          name      = "app"
          image     = var.container_image
          resources = { cpu = var.cpu, memory = var.memory }
          env = concat([for ref in var.secret_references : {
            name      = ref.environment_variable
            secretRef = ref.name
            }], [for name, value in var.environment_variables : {
            name  = name
            value = value
          }], local.telemetry_variables)
          probes = [
            {
              type             = "Startup"
              httpGet          = { path = "/health/live", port = var.target_port, scheme = "HTTP" }
              periodSeconds    = local.probe_settings.startup.periodSeconds
              timeoutSeconds   = local.probe_settings.startup.timeoutSeconds
              failureThreshold = local.probe_settings.startup.failureThreshold
            },
            {
              type                = "Liveness"
              httpGet             = { path = "/health/live", port = var.target_port, scheme = "HTTP" }
              initialDelaySeconds = local.probe_settings.liveness.initialDelaySeconds
              periodSeconds       = local.probe_settings.liveness.periodSeconds
              timeoutSeconds      = local.probe_settings.liveness.timeoutSeconds
              failureThreshold    = local.probe_settings.liveness.failureThreshold
            },
            {
              type                = "Readiness"
              httpGet             = { path = "/health/ready", port = var.target_port, scheme = "HTTP" }
              initialDelaySeconds = local.probe_settings.readiness.initialDelaySeconds
              periodSeconds       = local.probe_settings.readiness.periodSeconds
              timeoutSeconds      = local.probe_settings.readiness.timeoutSeconds
              failureThreshold    = local.probe_settings.readiness.failureThreshold
            }
          ]
        }]
        scale = {
          minReplicas = var.availability.min_replicas
          maxReplicas = var.availability.max_replicas
          rules       = [{ name = "http", http = { metadata = { concurrentRequests = "100" } } }]
        }
      }
    }
  }
  # Never export the full response or query listSecrets/listKeys.
  response_export_values = ["properties.configuration.ingress.fqdn"]
}

# Issued after the app carries the host name; the app refers to it by ID, avoiding a cycle.
resource "azapi_resource" "certificate" {
  count     = var.custom_domain == null ? 0 : 1
  type      = "Microsoft.App/managedEnvironments/managedCertificates@2025-07-01"
  name      = local.certificate_name
  parent_id = azapi_resource.environment.id
  location  = var.location
  tags      = local.tags
  body = {
    properties = {
      subjectName             = var.custom_domain.host_name
      domainControlValidation = "CNAME"
    }
  }
  response_export_values = []
  depends_on             = [azapi_resource.app]
}

# Without a client secret Easy Auth signs users in with an ID token only, so no credential is stored.
resource "azapi_resource" "auth" {
  count     = var.authentication == null ? 0 : 1
  type      = "Microsoft.App/containerApps/authConfigs@2025-07-01"
  name      = "current"
  parent_id = azapi_resource.app.id
  body = {
    properties = merge({
      platform = { enabled = true }
      globalValidation = merge(
        { unauthenticatedClientAction = local.auth_sign_in ? "RedirectToLoginPage" : "Return401" },
        local.auth_sign_in ? { redirectToProvider = "azureactivedirectory" } : {},
        length(coalesce(var.authentication.excluded_paths, [])) == 0 ? {} : { excludedPaths = var.authentication.excluded_paths },
      )
      identityProviders = {
        azureActiveDirectory = merge({
          enabled = true
          registration = {
            clientId     = var.authentication.client_id
            openIdIssuer = "https://login.microsoftonline.com/${var.authentication.tenant_id}/v2.0"
          }
          }, length(coalesce(var.authentication.allowed_audiences, [])) == 0 ? {} : {
          validation = { allowedAudiences = var.authentication.allowed_audiences }
        })
      }
      }, var.authentication.public_host_name == null ? {} : {
      # Operator-owned edges and custom domains forward the public host in X-Forwarded-Host.
      httpSettings = { forwardProxy = { convention = "Standard" } }
    })
  }
  response_export_values = []
}

locals {
  protected_resources = merge({
    app         = azapi_resource.app.id
    environment = azapi_resource.environment.id
    }, var.existing_log_analytics_workspace_resource_id == null ? { workspace = azapi_resource.workspace[0].id } : {},
  var.existing_identity_resource_id == null ? { identity = azapi_resource.identity[0].id } : {})
}

resource "azapi_resource" "protection" {
  for_each               = var.availability.deletion_protection ? local.protected_resources : {}
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "foundation-protection"
  parent_id              = each.value
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}
