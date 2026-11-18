// Public contract: parameters and outputs. Types and guards live in compile-time imports
// (common, environment, app, auth), so the deployment graph stays a single template.
import { authProperties, Authentication, callbackUrl, requireAuthentication } from './auth.bicep'
import {
  Availability
  CustomDomain
  PrivateEndpoint
  requireAvailability
  requireCustomDomain
  requireInternalEnvironment
  requireLinkedNetworks
  requirePrivateEndpoint
  requirePublicNetworkAccess
  requireWorkspaceId
} from './environment.bicep'
import {
  EnvironmentVariables
  requireDigest
  requireEnvironment
  requireIdentity
  requireName
  requireRegistry
  requireResources
  requireSecrets
  requireTelemetry
  SecretReference
} from './app.bicep'

@description('Azure region; must match the existing resource group/subnet placement policy.')
@minLength(1)
param location string

@minLength(2)
@maxLength(32)
param appName string

@minLength(2)
@maxLength(32)
param environmentName string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Explicit capacity and protection choices, including for development.')
param availability Availability

@description('Immutable registry/repository@sha256:<64 lowercase hex digits>.')
param containerImage string

@minValue(1)
@maxValue(65535)
param targetPort int = 8080

@description('vCPU per replica as a decimal string, from 0.25 to 4 in 0.25 steps.')
param cpu string = '0.5'

@description('Memory per replica; must be twice the cpu in Gi, such as 1Gi for 0.5.')
param memory string = '1Gi'

@minValue(30)
@maxValue(730)
@description('Log Analytics retention in days for the dedicated workspace.')
param logRetentionDays int = 30

@description('Caller-owned Log Analytics workspace ARM ID. Omit (null) to create the dedicated workspace; supplied IDs are never managed or locked.')
@minLength(1)
param existingLogAnalyticsWorkspaceResourceId string?

@description('Pre-authorized identity required for Key Vault or private ACR. Omit (null) to create an identity.')
@minLength(1)
param existingIdentityResourceId string?

@description('Optional ACR login server, without scheme. Operator grants image-pull access to the existing identity.')
@minLength(1)
param registryServer string?

@description('References only; no secret values. Operator grants Key Vault Secrets User before deployment.')
param secretReferences SecretReference[] = []

@description('Nonsecret environment values only. Use secretReferences for credentials; reserved names and duplicate destinations are rejected.')
param environmentVariables EnvironmentVariables = {}

@description('Optional Application Insights connection string, such as the application-insights output. Needs an existing identity granted Monitoring Metrics Publisher.')
@minLength(1)
param applicationInsightsConnectionString string?

@description('Optional https:// OTLP/HTTP base URL, such as Langfuse. Pass its headers as a secretReferences entry for OTEL_EXPORTER_OTLP_HEADERS.')
@minLength(1)
param otlpEndpoint string?

@description('Internal load balancer for VNet clients. Requires an infrastructure subnet; separate from app ingress.external.')
param internalEnvironment bool = false

@description('Extra VNet ARM IDs, such as a hub or peered VNets, linked to the internal environment DNS zone. Requires internalEnvironment.')
param linkedVirtualNetworkIds string[] = []

@allowed(['Enabled', 'Disabled'])
@description('Explicit environment public reachability; omit (null) to preserve the platform/previous setting. Internal environments and private endpoints always disable it and reject Enabled.')
param publicNetworkAccess string?

@description('Optional separate Private Link topology. Staging and prod require this or an internal environment, never both.')
param privateEndpoint PrivateEndpoint?

@description('Optional Microsoft Entra built-in authentication. Authorization by roles or groups stays in the app, using token claims.')
param authentication Authentication?

@description('Optional public subdomain with a free managed certificate. Deploy with bindCertificate false first, then true.')
param customDomain CustomDomain?

var settings = requireAvailability(stage, availability)
var internal = requireInternalEnvironment(internalEnvironment, availability.?infrastructureSubnetId, privateEndpoint)
var network = internal ? null : requirePrivateEndpoint(stage, location, privateEndpoint)
var publicAccess = requirePublicNetworkAccess(publicNetworkAccess, internal, privateEndpoint)
var linkedNetworks = requireLinkedNetworks(linkedVirtualNetworkIds, internal, availability.?infrastructureSubnetId)
var domain = requireCustomDomain(customDomain, internal, privateEndpoint, publicNetworkAccess)
var bound = domain.?bindCertificate ?? false
var resources = { cpu: json(requireResources(cpu, memory)), memory: memory }
var auth = requireAuthentication(authentication)
var image = requireDigest(containerImage)
var checkedAppName = requireName(appName)
var checkedEnvironmentName = requireName(environmentName)
var checkedIdentityId = requireIdentity(
  existingIdentityResourceId,
  !empty(secretReferences) || registryServer != null || applicationInsightsConnectionString != null
)
var checkedRegistry = requireRegistry(registryServer, image)
var checkedSecrets = requireSecrets(secretReferences)
var checkedEnvironment = requireEnvironment(environmentVariables, map(secretReferences, ref => ref.environmentVariable))
var telemetry = requireTelemetry(
  applicationInsightsConnectionString,
  otlpEndpoint,
  map(secretReferences, ref => ref.environmentVariable)
)
var tags = { stage: stage }
var checkedWorkspaceId = requireWorkspaceId(existingLogAnalyticsWorkspaceResourceId)
var workspaceId = checkedWorkspaceId ?? workspace!.id
var identityId = checkedIdentityId ?? identity!.id
var certificateName = '${checkedAppName}-cert'
var certificateId = '${environment.id}/managedCertificates/${certificateName}'
// Startup allows 30 x 10 s for a cold start; liveness and readiness then poll the health endpoints.
var probeSettings = {
  startup: { periodSeconds: 10, timeoutSeconds: 2, failureThreshold: 30 }
  liveness: { initialDelaySeconds: 10, periodSeconds: 10, timeoutSeconds: 2, failureThreshold: 3 }
  readiness: { initialDelaySeconds: 5, periodSeconds: 5, timeoutSeconds: 2, failureThreshold: 3 }
}

// Plain values only: the connection string is an identifier, not a credential.
// OTLP headers are credentials and arrive through secretReferences instead.
var telemetryVariables = concat(
  telemetry
    ? [
        { name: 'OTEL_SERVICE_NAME', value: checkedAppName }
        { name: 'OTEL_RESOURCE_ATTRIBUTES', value: 'deployment.environment.name=${stage}' }
      ]
    : [],
  applicationInsightsConnectionString == null
    ? []
    : [
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: applicationInsightsConnectionString }
        // Selects the user-assigned identity for Entra ID authenticated ingestion.
        { name: 'AZURE_CLIENT_ID', value: reference(checkedIdentityId!, '2024-11-30').clientId }
      ],
  otlpEndpoint == null
    ? []
    : [
        { name: 'OTEL_EXPORTER_OTLP_ENDPOINT', value: otlpEndpoint }
        // OpenTelemetry SDKs may default to gRPC; Langfuse accepts OTLP over HTTP only.
        { name: 'OTEL_EXPORTER_OTLP_PROTOCOL', value: 'http/protobuf' }
      ]
)

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = if (existingIdentityResourceId == null) {
  name: '${checkedAppName}-identity'
  location: location
  tags: tags
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' = if (checkedWorkspaceId == null) {
  name: '${checkedEnvironmentName}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: logRetentionDays
    features: {
      disableLocalAuth: true
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: checkedEnvironmentName
  location: location
  tags: tags
  properties: union(
    {
      appLogsConfiguration: { destination: 'azure-monitor' }
      zoneRedundant: settings.zoneRedundant
      // App ingress remains external=true so clients elsewhere in the VNet can reach it.
      vnetConfiguration: settings.?infrastructureSubnetId == null
        ? null
        : {
            infrastructureSubnetId: settings.infrastructureSubnetId!
            internal: internal
          }
      workloadProfiles: [
        { name: 'Consumption', workloadProfileType: 'Consumption' }
      ]
    },
    internal || network != null
      ? { publicNetworkAccess: 'Disabled' }
      : publicAccess == null ? {} : { publicNetworkAccess: publicAccess }
  )
}

// A nested deployment accepts the domain that is only known after ACA creation.
module internalDns './internal-dns.bicep' = if (internal) {
  name: '${checkedEnvironmentName}-dns'
  params: {
    domain: environment.properties.defaultDomain
    address: environment.properties.staticIp
    // Positional: a resource group or VNet literally named 'subnets' stays intact.
    networkId: join(take(split(settings.infrastructureSubnetId!, '/'), 9), '/')
    linkedNetworkIds: linkedNetworks
    name: checkedEnvironmentName
    tags: tags
    deletionProtection: settings.deletionProtection
  }
}

resource endpoint 'Microsoft.Network/privateEndpoints@2025-01-01' = if (network != null) {
  name: '${checkedEnvironmentName}-pe'
  location: location
  tags: tags
  properties: {
    subnet: { id: network!.subnetId }
    privateLinkServiceConnections: [
      {
        name: checkedEnvironmentName
        properties: {
          privateLinkServiceId: environment.id
          groupIds: ['managedEnvironments']
        }
      }
    ]
  }
}

resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01' = if (network != null) {
  parent: endpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'container-apps', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'container-apps-logs'
  scope: environment
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'ContainerAppConsoleLogs', enabled: true }
      { category: 'ContainerAppSystemLogs', enabled: true }
    ]
  }
}

resource app 'Microsoft.App/containerApps@2025-07-01' = {
  name: checkedAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: targetPort
        transport: 'http'
        // Declarative: removing customDomain also removes the host name binding.
        customDomains: domain == null
          ? []
          : [
              union(
                { name: domain!.hostName, bindingType: bound ? 'SniEnabled' : 'Disabled' },
                bound ? { certificateId: certificateId } : {}
              )
            ]
      }
      registries: checkedRegistry == null
        ? []
        : [
            { server: checkedRegistry, identity: identityId }
          ]
      secrets: [
        for secret in checkedSecrets: {
          name: secret.name
          keyVaultUrl: secret.keyVaultUrl
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'app'
          image: image
          resources: resources
          env: concat(
            map(checkedSecrets, secret => { name: secret.environmentVariable, secretRef: secret.name }),
            map(items(checkedEnvironment), entry => { name: entry.key, value: entry.value }),
            telemetryVariables
          )
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health/live', port: targetPort, scheme: 'HTTP' }
              periodSeconds: probeSettings.startup.periodSeconds
              timeoutSeconds: probeSettings.startup.timeoutSeconds
              failureThreshold: probeSettings.startup.failureThreshold
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health/live', port: targetPort, scheme: 'HTTP' }
              initialDelaySeconds: probeSettings.liveness.initialDelaySeconds
              periodSeconds: probeSettings.liveness.periodSeconds
              timeoutSeconds: probeSettings.liveness.timeoutSeconds
              failureThreshold: probeSettings.liveness.failureThreshold
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health/ready', port: targetPort, scheme: 'HTTP' }
              initialDelaySeconds: probeSettings.readiness.initialDelaySeconds
              periodSeconds: probeSettings.readiness.periodSeconds
              timeoutSeconds: probeSettings.readiness.timeoutSeconds
              failureThreshold: probeSettings.readiness.failureThreshold
            }
          ]
        }
      ]
      scale: {
        minReplicas: settings.minReplicas
        maxReplicas: settings.maxReplicas
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '100' } }
          }
        ]
      }
    }
  }
}

// Issued after the app carries the host name; the app refers to it by ID, avoiding a cycle.
resource certificate 'Microsoft.App/managedEnvironments/managedCertificates@2025-07-01' = if (domain != null) {
  parent: environment
  name: certificateName
  location: location
  tags: tags
  properties: {
    subjectName: domain!.hostName
    domainControlValidation: 'CNAME'
  }
  dependsOn: [app]
}

resource authConfig 'Microsoft.App/containerApps/authConfigs@2025-07-01' = if (auth != null) {
  parent: app
  name: 'current'
  properties: authProperties(auth!)
}

// Resource-scoped locks never protect unrelated resources in the caller's group.
resource appLock 'Microsoft.Authorization/locks@2020-05-01' = if (settings.deletionProtection) {
  name: 'foundation-protection'
  scope: app
  properties: { level: 'CanNotDelete' }
}

resource environmentLock 'Microsoft.Authorization/locks@2020-05-01' = if (settings.deletionProtection) {
  name: 'foundation-protection'
  scope: environment
  properties: { level: 'CanNotDelete' }
}

resource workspaceLock 'Microsoft.Authorization/locks@2020-05-01' = if (settings.deletionProtection && checkedWorkspaceId == null) {
  name: 'foundation-protection'
  scope: workspace
  properties: { level: 'CanNotDelete' }
}

resource identityLock 'Microsoft.Authorization/locks@2020-05-01' = if (settings.deletionProtection && existingIdentityResourceId == null) {
  name: 'foundation-protection'
  scope: identity
  properties: { level: 'CanNotDelete' }
}

output appResourceId string = app.id
output environmentResourceId string = environment.id
output workspaceResourceId string = workspaceId
output managedIdentityResourceId string = identityId
output url string = 'https://${app.properties.configuration.ingress!.fqdn}'
// <unique>.<location>.azurecontainerapps.io; its first label is the private DNS record name.
output environmentDefaultDomain string = environment.properties.defaultDomain
output privateEndpointResourceId string? = network == null ? null : endpoint!.id
// Redirect URI to register on the Entra app; null unless authentication.signIn is true.
output authCallbackUrl string? = callbackUrl(auth, domain.?hostName ?? app.properties.configuration.ingress!.fqdn)
// Custom domain DNS: CNAME <hostName> to this target, and TXT asuid.<hostName> with the verification ID.
output customDomainCnameTarget string = app.properties.configuration.ingress!.fqdn
output customDomainTxtRecordName string? = domain == null ? null : 'asuid.${domain!.hostName}'
output customDomainVerificationId string? = environment.properties.?customDomainConfiguration.?customDomainVerificationId
