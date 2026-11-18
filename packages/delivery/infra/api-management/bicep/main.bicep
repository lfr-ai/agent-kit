// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireBackendUrl(url string) string =>
  take(url, 8) == 'https://' && length(url) > 8 ? url : fail('backendUrl must be an https:// URL.')

@export()
func requireTokenValidation(stage string, tenantId string?, audience string?) string? =>
  (tenantId == null) != (audience == null)
    ? fail('entraTenantId and entraAudience must be set together.')
    : tenantId == null
        ? contains(['staging', 'prod'], stage)
            ? fail('Staging and production require entraTenantId and entraAudience: callers must present an Entra token.')
            : tenantId
        : empty(tenantId!) || empty(audience!)
            ? fail('entraTenantId and entraAudience must be omitted or non-empty.')
            : tenantId

@export()
func requireApplicationInsights(llmTokensPerMinute int, applicationInsightsName string?) string? =>
  applicationInsightsName == null
    ? llmTokensPerMinute > 0
        ? fail('llmTokensPerMinute needs applicationInsightsName to publish token metrics.')
        : applicationInsightsName
    : empty(applicationInsightsName!)
        ? fail('applicationInsightsName must be omitted or non-empty.')
        : applicationInsightsName

@export()
func requireWorkspace(stage string, workspaceId string?) string? =>
  workspaceId == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for gateway logs.')
        : workspaceId
    : empty(workspaceId!) ? fail('logAnalyticsWorkspaceId must be omitted or non-empty.') : workspaceId

@description('Azure region for the API Management instance.')
@minLength(1)
param location string

@description('Globally unique name; the gateway is https://<name>.azure-api.net. Use a distinct name per stage.')
@minLength(1)
@maxLength(50)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Email address that receives API Management system notifications.')
@minLength(1)
param publisherEmail string

@description('HTTPS base URL of the backend the API fronts, for example a Container App URL.')
param backendUrl string

@description('Entra tenant that issues caller tokens; set with entraAudience. Required in staging and production.')
@minLength(1)
param entraTenantId string?

@description('Application ID URI or client ID that caller tokens must target; set with entraTenantId.')
@minLength(1)
param entraAudience string?

@description('Calls per minute for each caller: the token subject, or the client IP without token validation.')
@minValue(1)
param requestsPerMinute int = 120

@description('LLM tokens per minute for each caller; 0 leaves the AI gateway policies out. Needs applicationInsightsName.')
@minValue(0)
param llmTokensPerMinute int = 0

@description('Existing Application Insights component in this resource group for gateway telemetry; omit for none.')
@minLength(1)
param applicationInsightsName string?

@description('Existing Log Analytics workspace ARM ID for gateway logs; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var serviceUrl = requireBackendUrl(backendUrl)
var tenantId = requireTokenValidation(stage, entraTenantId, entraAudience)
var insightsName = requireApplicationInsights(llmTokensPerMinute, applicationInsightsName)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }
var metricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

// Optional fragments replace marker comments, so every policy file stays well-formed XML.
var tokenValidation = tenantId == null
  ? ''
  : replace(
      replace(loadTextContent('../policies/validate-token.xml'), '{tenant-id}', tenantId!),
      '{audience}',
      entraAudience!
    )
var llmTokens = llmTokensPerMinute == 0
  ? ''
  : replace(loadTextContent('../policies/llm-tokens.xml'), '{tokens-per-minute}', string(llmTokensPerMinute))
var apiPolicy = replace(
  replace(
    replace(loadTextContent('../policies/api.xml'), '<!-- validate-token -->', trim(tokenValidation)),
    '<!-- llm-tokens -->',
    trim(llmTokens)
  ),
  '{requests-per-minute}',
  string(requestsPerMinute)
)

// Basic v2 is the dev/test tier. Production uses Standard v2: Microsoft's production v2 tier,
// with inbound private endpoints for an optional operator-owned edge and outbound VNet integration.
// Staging keeps Basic v2 for cost; it shares the production token and workspace guards, not the tier.
resource service 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: stage == 'prod' ? 'StandardV2' : 'BasicV2'
    capacity: 1
  }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: publisherEmail
    // Required by the API; shown only in the developer portal and notification emails.
    publisherName: name
  }
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: service
  name: 'backend'
  properties: {
    displayName: 'Backend'
    path: ''
    serviceUrl: serviceUrl
    protocols: ['https']
    // Callers are identified by Entra tokens, never by subscription keys.
    subscriptionRequired: false
  }
}

// Wildcard operations forward every path; an API without operations answers 404.
resource operations 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = [
  for method in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']: {
    parent: api
    name: toLower(method)
    properties: {
      displayName: method
      method: method
      urlTemplate: '/*'
    }
  }
]

resource policy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: { value: apiPolicy }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = if (insightsName != null) {
  // ARM evaluates names of skipped resources, so an absent component keeps a placeholder.
  name: insightsName ?? ''
}

// The logger authenticates with the system identity, so ingestion needs no key.
resource metricsPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (insightsName != null) {
  name: guid(applicationInsights.id, service.id, metricsPublisherRoleId)
  scope: applicationInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', metricsPublisherRoleId)
    principalId: service.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource logger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = if (insightsName != null) {
  parent: service
  name: 'application-insights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: applicationInsights.id
    credentials: {
      // Read from the component, never a parameter; it identifies the target, it does not authorize.
      connectionString: applicationInsights!.properties.ConnectionString
      identityClientId: 'SystemAssigned'
    }
  }
  dependsOn: [metricsPublisher]
}

// metrics: true lets llm-emit-token-metric publish custom metrics.
resource telemetry 'Microsoft.ApiManagement/service/diagnostics@2024-05-01' = if (insightsName != null) {
  parent: service
  name: 'applicationinsights'
  properties: {
    loggerId: logger.id
    metrics: true
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'gateway-logs'
  scope: service
  properties: {
    workspaceId: workspaceId!
    // Resource-specific ApiManagementGatewayLogs table instead of AzureDiagnostics.
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      { category: 'GatewayLogs', enabled: true }
    ]
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: service
  properties: { level: 'CanNotDelete' }
}

@description('API Management instance ARM ID; an optional operator-owned edge may target it.')
output apiManagementResourceId string = service.id
@description('Gateway base URL; the API is served at its root.')
output gatewayUrl string = service.properties.gatewayUrl
@description('Grant this identity access to the backend when it needs authentication-managed-identity.')
output principalId string = service.identity.principalId
