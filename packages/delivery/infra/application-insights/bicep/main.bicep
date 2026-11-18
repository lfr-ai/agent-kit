// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireWorkspaceId(value string) string =>
  startsWith(value, '/subscriptions/') && contains(toLower(value), '/microsoft.operationalinsights/workspaces/')
    ? value
    : fail('logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID.')

@export()
func requirePrincipalId(value string) string =>
  length(value) == 36 && length(split(value, '-')) == 5
    ? value
    : fail('principalId must be the object (principal) ID GUID of the existing app identity.')

@description('Azure region; normally the workspace region.')
@minLength(1)
param location string

@description('Application Insights resource name. Use a distinct name per stage.')
@minLength(1)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('ARM ID of the existing Log Analytics workspace that stores the telemetry.')
param logAnalyticsWorkspaceId string

@description('Object (principal) ID of the existing app identity that publishes telemetry.')
param principalId string

var workspaceId = requireWorkspaceId(logAnalyticsWorkspaceId)
var objectId = requirePrincipalId(principalId)
// Monitoring Metrics Publisher: the built-in role for Entra ID authenticated ingestion.
var publisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

// Only non-defaults are declared: public ingestion and query, sampling, IP
// masking and retention (owned by the workspace) stay at platform defaults.
resource component 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  tags: { stage: stage }
  // Required by this API version.
  kind: 'web'
  properties: {
    // Required by this API version.
    Application_Type: 'web'
    WorkspaceResourceId: workspaceId
    // dev keeps instrumentation-key ingestion for local runs; test, staging and prod accept Entra ID only.
    DisableLocalAuth: stage != 'dev'
  }
}

resource publisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(component.id, objectId, publisherRoleId)
  scope: component
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', publisherRoleId)
    principalId: objectId
    // Lets ARM assign a newly created managed identity before Entra ID replication completes.
    principalType: 'ServicePrincipal'
  }
}

output applicationInsightsResourceId string = component.id
// An identifier, not a credential: test and prod ingestion still needs an Entra ID token.
output connectionString string = component.properties.ConnectionString
