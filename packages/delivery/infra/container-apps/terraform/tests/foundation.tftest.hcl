# Every run is a plan against a mocked Azure provider, never an apply.
mock_provider "azapi" {
  mock_data "azapi_resource" {
    defaults = {
      output = { properties = { clientId = "11111111-1111-1111-1111-111111111111" } }
    }
  }
}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  app_name          = "sample-dev"
  environment_name  = "sample-dev-env"
  stage             = "dev"
  # Synthetic digest: not a runnable image.
  container_image = "example.azurecr.io/sample@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  availability = {
    min_replicas        = 0
    max_replicas        = 3
    zone_redundant      = false
    deletion_protection = false
    # No infrastructure_subnet_id: a dev environment without VNet integration.
  }
}

run "development" {
  command = plan

  assert {
    condition     = azapi_resource.app.body.properties.configuration.ingress.allowInsecure == false
    error_message = "Ingress must not allow plaintext HTTP."
  }
  assert {
    condition     = azapi_resource.app.body.properties.template.containers[0].image == var.container_image
    error_message = "Use the supplied immutable image."
  }
  assert {
    condition     = [for probe in azapi_resource.app.body.properties.template.containers[0].probes : probe.httpGet.path] == ["/health/live", "/health/live", "/health/ready"]
    error_message = "Startup/liveness/readiness paths drifted."
  }
  assert {
    condition     = azapi_resource.environment.body.properties.appLogsConfiguration.destination == "azure-monitor" && azapi_resource.workspace[0].body.properties.features.disableLocalAuth
    error_message = "Logging must not use workspace shared keys."
  }
  assert {
    condition     = length(azapi_resource.protection) == 0 && length(azapi_resource.identity) == 1
    error_message = "Development choices or dedicated identity drifted."
  }
  assert {
    condition     = azapi_resource.app.body.properties.template.containers[0].env == []
    error_message = "Without secret references or telemetry the app gets no environment variables."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 0 && length(azapi_resource.dns_zone_group) == 0 && !contains(keys(azapi_resource.environment.body.properties), "publicNetworkAccess")
    error_message = "Without private_endpoint the environment keeps its default network access and no endpoint."
  }
  assert {
    condition     = output.private_endpoint_resource_id == null
    error_message = "Without private_endpoint the endpoint output is null."
  }
  assert {
    condition     = length(azapi_resource.auth) == 0 && output.auth_callback_url == null
    error_message = "Without authentication no authConfigs resource or callback URL exists."
  }
  assert {
    condition = (
      azapi_resource.app.body.properties.template.containers[0].resources == { cpu = 0.5, memory = "1Gi" } &&
      azapi_resource.workspace[0].body.properties.retentionInDays == 30
    )
    error_message = "Default resources and log retention drifted."
  }
  assert {
    condition = (
      length(azapi_resource.certificate) == 0 && output.custom_domain_txt_record_name == null &&
      length(azapi_resource.app.body.properties.configuration.ingress.customDomains) == 0
    )
    error_message = "Without custom_domain no certificate or host name binding exists."
  }
}

run "resources_and_retention" {
  command = plan
  variables {
    cpu                = 1.25
    memory             = "2.5Gi"
    log_retention_days = 90
  }
  assert {
    condition = (
      azapi_resource.app.body.properties.template.containers[0].resources == { cpu = 1.25, memory = "2.5Gi" } &&
      azapi_resource.workspace[0].body.properties.retentionInDays == 90
    )
    error_message = "cpu, memory and log_retention_days must reach the app and workspace."
  }
}

run "reject_resource_pair" {
  command = plan
  variables {
    cpu    = 1
    memory = "1Gi"
  }
  expect_failures = [var.memory]
}

run "reject_log_retention" {
  command = plan
  variables {
    log_retention_days = 7
  }
  expect_failures = [var.log_retention_days]
}

# Second phase: the certificate exists, so the host name binds with SNI.
run "custom_domain_bound" {
  command = plan
  # The environment ID is known only after apply; pin it so the certificate ID can be asserted.
  override_resource {
    target          = azapi_resource.environment
    override_during = plan
    values = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.App/managedEnvironments/sample-dev-env"
      output = {
        properties = {
          defaultDomain             = "example.westeurope.azurecontainerapps.io"
          staticIp                  = "10.0.0.4"
          customDomainConfiguration = { customDomainVerificationId = "0000" }
        }
      }
    }
  }
  variables {
    custom_domain = {
      host_name        = "app.example.com"
      bind_certificate = true
    }
    authentication = {
      client_id = "22222222-2222-2222-2222-222222222222"
      tenant_id = "33333333-3333-3333-3333-333333333333"
      sign_in   = true
    }
  }
  assert {
    condition = (
      azapi_resource.certificate[0].name == "sample-dev-cert" &&
      azapi_resource.certificate[0].body.properties == { subjectName = "app.example.com", domainControlValidation = "CNAME" }
    )
    error_message = "The managed certificate must validate the host name by CNAME."
  }
  assert {
    condition = (
      azapi_resource.app.body.properties.configuration.ingress.customDomains[0].name == "app.example.com" &&
      azapi_resource.app.body.properties.configuration.ingress.customDomains[0].bindingType == "SniEnabled" &&
      endswith(azapi_resource.app.body.properties.configuration.ingress.customDomains[0].certificateId, "/managedCertificates/sample-dev-cert")
    )
    error_message = "A bound custom domain uses SNI with the managed certificate."
  }
  assert {
    condition     = output.custom_domain_txt_record_name == "asuid.app.example.com" && output.auth_callback_url == "https://app.example.com/.auth/login/aad/callback"
    error_message = "Custom domain outputs and the callback URL must use the host name."
  }
}

# First phase: the host name is added unbound while the certificate is issued.
run "custom_domain_unbound" {
  command = plan
  variables {
    custom_domain = {
      host_name = "app.example.com"
    }
  }
  assert {
    condition = (
      azapi_resource.app.body.properties.configuration.ingress.customDomains[0].bindingType == "Disabled" &&
      !contains(keys(azapi_resource.app.body.properties.configuration.ingress.customDomains[0]), "certificateId")
    )
    error_message = "An unbound custom domain carries no certificate ID."
  }
}

run "reject_custom_domain_on_private_endpoint" {
  command = plan
  variables {
    custom_domain = {
      host_name = "app.example.com"
    }
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.westeurope.azurecontainerapps.io"
    }
  }
  expect_failures = [var.custom_domain]
}

run "reject_apex_custom_domain" {
  command = plan
  variables {
    custom_domain = {
      host_name = "example.com"
    }
  }
  expect_failures = [var.custom_domain]
}

run "authentication_api" {
  command = plan
  variables {
    authentication = {
      client_id         = "22222222-2222-2222-2222-222222222222"
      tenant_id         = "33333333-3333-3333-3333-333333333333"
      allowed_audiences = ["api://22222222-2222-2222-2222-222222222222"]
    }
  }
  assert {
    condition = (
      azapi_resource.auth[0].name == "current" &&
      azapi_resource.auth[0].body.properties.globalValidation == { unauthenticatedClientAction = "Return401" } &&
      azapi_resource.auth[0].body.properties.identityProviders.azureActiveDirectory.registration == {
        clientId     = "22222222-2222-2222-2222-222222222222"
        openIdIssuer = "https://login.microsoftonline.com/33333333-3333-3333-3333-333333333333/v2.0"
      } &&
      azapi_resource.auth[0].body.properties.identityProviders.azureActiveDirectory.validation.allowedAudiences == tolist(["api://22222222-2222-2222-2222-222222222222"])
    )
    error_message = "API mode accepts bearer tokens only and returns 401 without one."
  }
  assert {
    condition     = !contains(keys(azapi_resource.auth[0].body.properties), "httpSettings") && azapi_resource.app.body.properties.configuration.secrets == [] && output.auth_callback_url == null
    error_message = "API mode needs no secret, forward proxy or callback URL."
  }
}

run "authentication_sign_in" {
  command = plan
  variables {
    authentication = {
      client_id        = "22222222-2222-2222-2222-222222222222"
      tenant_id        = "33333333-3333-3333-3333-333333333333"
      sign_in          = true
      public_host_name = "app.example.com"
    }
  }
  assert {
    condition = azapi_resource.auth[0].body.properties.globalValidation == {
      unauthenticatedClientAction = "RedirectToLoginPage"
      redirectToProvider          = "azureactivedirectory"
    }
    error_message = "Browser sign-in redirects to Microsoft Entra."
  }
  assert {
    condition     = !contains(keys(azapi_resource.auth[0].body.properties.identityProviders.azureActiveDirectory.registration), "clientSecretSettingName") && azapi_resource.app.body.properties.configuration.secrets == []
    error_message = "Browser sign-in must stay secretless."
  }
  assert {
    condition     = azapi_resource.auth[0].body.properties.httpSettings.forwardProxy.convention == "Standard" && output.auth_callback_url == "https://app.example.com/.auth/login/aad/callback"
    error_message = "A public host name trusts X-Forwarded-Host and sets the callback URL."
  }
}

run "reject_authentication_without_guid" {
  command = plan
  variables {
    authentication = {
      client_id = "not-a-guid"
      tenant_id = "33333333-3333-3333-3333-333333333333"
    }
  }
  expect_failures = [var.authentication]
}

run "production" {
  command = plan
  variables {
    stage = "prod"
    availability = {
      min_replicas             = 2
      max_replicas             = 10
      zone_redundant           = true
      deletion_protection      = true
      infrastructure_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
    }
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.westeurope.azurecontainerapps.io"
    }
  }
  assert {
    condition     = azapi_resource.environment.body.properties.zoneRedundant && azapi_resource.app.body.properties.template.scale.minReplicas == 2 && length(azapi_resource.protection) == 4
    error_message = "Production must protect all owned resources and require availability."
  }
  assert {
    condition     = azapi_resource.environment.body.properties.publicNetworkAccess == "Disabled" && azapi_resource.environment.body.properties.vnetConfiguration.internal == false
    error_message = "Production must disable public network access on an external environment."
  }
  assert {
    condition = (
      azapi_resource.endpoint[0].body.properties.subnet.id == var.private_endpoint.subnet_id &&
      jsonencode(azapi_resource.endpoint[0].body.properties.privateLinkServiceConnections[0].properties.groupIds) == jsonencode(["managedEnvironments"])
    )
    error_message = "The private endpoint must target the environment's managedEnvironments sub-resource in the supplied subnet."
  }
  assert {
    condition     = length(azapi_resource.dns_zone_group) == 1 && azapi_resource.dns_zone_group[0].body.properties.privateDnsZoneConfigs[0].properties.privateDnsZoneId == var.private_endpoint.private_dns_zone_id
    error_message = "Production must register the endpoint in the supplied private DNS zone."
  }
}

# A private endpoint needs a workload-profiles environment, not VNet integration.
run "private_endpoint_without_subnet" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.westeurope.azurecontainerapps.io"
    }
  }
  assert {
    condition     = azapi_resource.environment.body.properties.publicNetworkAccess == "Disabled" && !contains(keys(azapi_resource.environment.body.properties), "vnetConfiguration")
    error_message = "Development may use a private endpoint without an infrastructure subnet."
  }
  assert {
    condition     = length(azapi_resource.endpoint) == 1 && length(azapi_resource.dns_zone_group) == 1 && azapi_resource.app.body.properties.configuration.ingress.external
    error_message = "Ingress stays external so that the private endpoint can reach the app."
  }
}

run "external_access" {
  command = plan
  variables {
    existing_identity_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    registry_server               = "example.azurecr.io"
    secret_references = [{
      name                 = "external-token"
      environment_variable = "EXTERNAL_TOKEN"
      key_vault_url        = "https://example.vault.azure.net/secrets/external-token"
    }]
    environment_variables = {
      APP_POSTGRES_HOST = "db.example.invalid"
      APP_AUTH_SCOPES   = "[\"read\"]"
    }
  }
  assert {
    condition     = length(azapi_resource.identity) == 0 && azapi_resource.app.body.properties.configuration.registries[0].identity == var.existing_identity_resource_id
    error_message = "External identity must be reused, not created or password-authenticated."
  }
  assert {
    condition     = azapi_resource.app.body.properties.configuration.secrets[0].keyVaultUrl == var.secret_references[0].key_vault_url && !contains(keys(azapi_resource.app.body.properties.configuration.secrets[0]), "value")
    error_message = "Only Key Vault references may enter the app configuration."
  }
  assert {
    condition = azapi_resource.app.body.properties.template.containers[0].env == [
      { name = "EXTERNAL_TOKEN", secretRef = "external-token" },
      { name = "APP_AUTH_SCOPES", value = "[\"read\"]" },
      { name = "APP_POSTGRES_HOST", value = "db.example.invalid" },
    ]
    error_message = "Nonsecret settings and Key Vault destinations must arrive unchanged without raw credentials."
  }
}

run "telemetry" {
  command = plan
  variables {
    existing_identity_resource_id          = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    application_insights_connection_string = "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://westeurope-5.in.applicationinsights.azure.com/"
    otlp_endpoint                          = "https://cloud.langfuse.com/api/public/otel"
    secret_references = [{
      name                 = "otlp-headers"
      environment_variable = "OTEL_EXPORTER_OTLP_HEADERS"
      key_vault_url        = "https://example.vault.azure.net/secrets/otlp-headers"
    }]
  }
  assert {
    condition = azapi_resource.app.body.properties.template.containers[0].env == [
      { name = "OTEL_EXPORTER_OTLP_HEADERS", secretRef = "otlp-headers" },
      { name = "OTEL_SERVICE_NAME", value = "sample-dev" },
      { name = "OTEL_RESOURCE_ATTRIBUTES", value = "deployment.environment.name=dev" },
      { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = var.application_insights_connection_string },
      { name = "AZURE_CLIENT_ID", value = "11111111-1111-1111-1111-111111111111" },
      { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "https://cloud.langfuse.com/api/public/otel" },
      { name = "OTEL_EXPORTER_OTLP_PROTOCOL", value = "http/protobuf" },
    ]
    error_message = "Telemetry must add plain routing variables and keep OTLP headers in Key Vault."
  }
}

run "preserve_lowercase_settings" {
  command = plan
  variables {
    existing_identity_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    environment_variables = {
      app_postgres_host = "db.example.invalid"
    }
    secret_references = [{
      name                 = "password"
      environment_variable = "app_postgres_password"
      key_vault_url        = "https://example.vault.azure.net/secrets/password"
    }]
  }
  assert {
    condition = azapi_resource.app.body.properties.template.containers[0].env == [
      { name = "app_postgres_password", secretRef = "password" },
      { name = "app_postgres_host", value = "db.example.invalid" },
    ]
    error_message = "Case-insensitive validation must preserve accepted names and Key Vault references."
  }
}

run "reject_lowercase_plain_credential" {
  command = plan
  variables {
    environment_variables = {
      app_postgres_password = "forbidden-test-value"
    }
  }
  expect_failures = [var.environment_variables]
}

run "reject_case_variant_reserved_plain" {
  command = plan
  variables {
    environment_variables = {
      aZuRe_ClIeNt_Id = "forbidden-test-value"
    }
  }
  expect_failures = [var.environment_variables]
}

# A client secret, certificate or federated token would make DefaultAzureCredential
# bypass the managed identity, so these names are rejected as plain values and references.
run "reject_credential_override_plain" {
  command = plan
  variables {
    environment_variables = {
      azure_federated_token_file = "/var/run/secrets/token"
    }
  }
  expect_failures = [var.environment_variables]
}

run "reject_credential_override_secret" {
  command = plan
  variables {
    existing_identity_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    secret_references = [{
      name                 = "client-secret"
      environment_variable = "AZURE_CLIENT_SECRET"
      key_vault_url        = "https://example.vault.azure.net/secrets/client-secret"
    }]
  }
  expect_failures = [var.secret_references]
}

run "reject_case_variant_reserved_secret" {
  command = plan
  variables {
    existing_identity_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    secret_references = [{
      name                 = "client"
      environment_variable = "azure_client_id"
      key_vault_url        = "https://example.vault.azure.net/secrets/client"
    }]
  }
  expect_failures = [var.secret_references]
}

run "reject_mixed_case_plain_secret_collision" {
  command = plan
  variables {
    existing_identity_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    environment_variables = {
      aPp_ToKeN = "forbidden-test-value"
    }
    secret_references = [{
      name                 = "token"
      environment_variable = "APP_TOKEN"
      key_vault_url        = "https://example.vault.azure.net/secrets/token"
    }]
  }
  expect_failures = [var.environment_variables]
}

run "reject_lowercase_credential_overriding_secret" {
  command = plan
  variables {
    existing_identity_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    environment_variables = {
      app_postgres_password = "forbidden-test-value"
    }
    secret_references = [{
      name                 = "password"
      environment_variable = "APP_POSTGRES_PASSWORD"
      key_vault_url        = "https://example.vault.azure.net/secrets/password"
    }]
  }
  expect_failures = [var.environment_variables]
}

run "reject_mixed_case_secret_secret_collision" {
  command = plan
  variables {
    existing_identity_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/access/providers/Microsoft.ManagedIdentity/userAssignedIdentities/apps"
    secret_references = [
      {
        name                 = "first"
        environment_variable = "APP_TOKEN"
        key_vault_url        = "https://example.vault.azure.net/secrets/first"
      },
      {
        name                 = "second"
        environment_variable = "aPp_ToKeN"
        key_vault_url        = "https://example.vault.azure.net/secrets/second"
      },
    ]
  }
  expect_failures = [var.secret_references]
}

run "reject_mixed_case_plain_plain_collision" {
  command = plan
  variables {
    environment_variables = {
      APP_VALUE = "first"
      app_value = "second"
    }
  }
  expect_failures = [var.environment_variables]
}

run "reject_telemetry_without_identity" {
  command = plan
  variables {
    application_insights_connection_string = "InstrumentationKey=00000000-0000-0000-0000-000000000000"
  }
  expect_failures = [var.application_insights_connection_string]
}

run "reject_mutable_image" {
  command = plan
  variables {
    container_image = "example.azurecr.io/sample:latest"
  }
  expect_failures = [var.container_image]
}

run "reject_production_defaults" {
  command = plan
  variables {
    stage = "prod"
  }
  expect_failures = [var.availability, var.private_endpoint]
}

run "reject_production_without_private_endpoint" {
  command = plan
  variables {
    stage = "prod"
    availability = {
      min_replicas             = 2
      max_replicas             = 10
      zone_redundant           = true
      deletion_protection      = true
      infrastructure_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
    }
  }
  expect_failures = [var.private_endpoint]
}

run "reject_internal_without_subnet" {
  command = plan
  variables {
    internal_environment = true
  }
  expect_failures = [var.availability]
}

run "reject_internal_with_private_endpoint" {
  command = plan
  variables {
    internal_environment = true
    availability = {
      min_replicas             = 0
      max_replicas             = 3
      zone_redundant           = false
      deletion_protection      = false
      infrastructure_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
    }
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.westeurope.azurecontainerapps.io"
    }
  }
  expect_failures = [var.private_endpoint]
}

# The internal environment publishes its domain through a VNet-linked private zone.
run "production_internal" {
  command = plan
  variables {
    stage                = "prod"
    internal_environment = true
    availability = {
      min_replicas        = 2
      max_replicas        = 3
      zone_redundant      = true
      deletion_protection = true
      # A resource group named like the child segment must not truncate the VNet ID.
      infrastructure_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/subnets/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
    }
  }
  assert {
    condition     = azapi_resource.environment.body.properties.vnetConfiguration.internal && length(azapi_resource.endpoint) == 0
    error_message = "An internal environment uses its VNet load balancer, not a private endpoint."
  }
  assert {
    condition     = azapi_resource.internal_dns_link[0].body.properties.virtualNetwork.id == "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/subnets/providers/Microsoft.Network/virtualNetworks/example"
    error_message = "The private zone must link the infrastructure subnet's own VNet."
  }
  assert {
    condition     = length(azapi_resource.internal_dns) == 1 && join(",", sort(keys(azapi_resource.internal_dns_records))) == "*,@" && length(azapi_resource.internal_dns_protection) == 1
    error_message = "Internal DNS needs one protected zone with wildcard and apex records."
  }
  assert {
    condition     = azapi_resource.internal_dns_protection[0].name == "foundation-protection" && length(azapi_resource.internal_dns_extra_links) == 0
    error_message = "The internal DNS lock shares the module lock name; no extra links by default."
  }
}

# Staging is prod-like for resilience but keeps deletion protection optional.
run "staging_internal_with_hub" {
  command = plan
  variables {
    stage                      = "staging"
    internal_environment       = true
    linked_virtual_network_ids = ["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/hub/providers/Microsoft.Network/virtualNetworks/Hub"]
    availability = {
      min_replicas             = 2
      max_replicas             = 3
      zone_redundant           = true
      deletion_protection      = false
      infrastructure_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
    }
  }
  assert {
    condition = (
      azapi_resource.internal_dns_extra_links["/subscriptions/00000000-0000-0000-0000-000000000000/resourcegroups/hub/providers/microsoft.network/virtualnetworks/hub"].name == "sample-dev-env-${uuidv5("11fb06fb-712d-4ddd-98c7-e71bbd588830", "/subscriptions/00000000-0000-0000-0000-000000000000/resourcegroups/hub/providers/microsoft.network/virtualnetworks/hub")}" &&
      azapi_resource.internal_dns_extra_links["/subscriptions/00000000-0000-0000-0000-000000000000/resourcegroups/hub/providers/microsoft.network/virtualnetworks/hub"].body.properties.virtualNetwork.id == var.linked_virtual_network_ids[0]
    )
    error_message = "Extra VNets get one deterministic link each, named like Bicep guid(toLower(id))."
  }
  assert {
    condition     = length(azapi_resource.internal_dns_protection) == 0 && length(azapi_resource.protection) == 0
    error_message = "Staging keeps deletion protection as an explicit choice."
  }
}

run "reject_staging_single_replica" {
  command = plan
  variables {
    stage                = "staging"
    internal_environment = true
    availability = {
      min_replicas             = 1
      max_replicas             = 3
      zone_redundant           = true
      deletion_protection      = false
      infrastructure_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
    }
  }
  expect_failures = [var.availability]
}

run "reject_linked_networks_without_internal" {
  command = plan
  variables {
    linked_virtual_network_ids = ["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/hub/providers/Microsoft.Network/virtualNetworks/hub"]
  }
  expect_failures = [var.linked_virtual_network_ids]
}

run "reject_public_access_on_internal" {
  command = plan
  variables {
    internal_environment  = true
    public_network_access = "Enabled"
    availability = {
      min_replicas             = 0
      max_replicas             = 3
      zone_redundant           = false
      deletion_protection      = false
      infrastructure_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/apps"
    }
  }
  expect_failures = [var.public_network_access]
}

run "reject_private_dns_zone_of_other_region" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.northeurope.azurecontainerapps.io"
    }
  }
  expect_failures = [var.private_endpoint]
}

run "reject_private_dns_zone_of_other_service" {
  command = plan
  variables {
    private_endpoint = {
      subnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints"
      private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net"
    }
  }
  expect_failures = [var.private_endpoint]
}
