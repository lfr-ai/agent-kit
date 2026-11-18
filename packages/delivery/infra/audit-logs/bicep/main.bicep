// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireWorkspaceId(value string) string =>
  startsWith(value, '/subscriptions/') && contains(toLower(value), '/microsoft.operationalinsights/workspaces/')
    ? value
    : fail('logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID.')

@export()
func requireActionGroupId(value string) string =>
  startsWith(value, '/subscriptions/') && contains(toLower(value), '/microsoft.insights/actiongroups/')
    ? value
    : fail('actionGroupId must be an action group ARM ID, for example the container-apps-alerts output.')

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('ARM ID of the existing Log Analytics workspace that receives the subscription Activity Log.')
param logAnalyticsWorkspaceId string

@description('ARM ID of the existing action group that receives the alerts.')
param actionGroupId string

@description('Alert on role assignment, policy assignment and policy exemption changes. On by default in staging and prod.')
param alertOnAccessChanges bool = contains(['staging', 'prod'], stage)

var workspaceId = requireWorkspaceId(logAnalyticsWorkspaceId)
var notify = { actionGroups: [{ actionGroupId: requireActionGroupId(actionGroupId) }] }
var tags = { stage: stage }
var accessOperations = [
  'Microsoft.Authorization/roleAssignments/write'
  'Microsoft.Authorization/roleAssignments/delete'
  'Microsoft.Authorization/policyAssignments/write'
  'Microsoft.Authorization/policyAssignments/delete'
  'Microsoft.Authorization/policyExemptions/write'
  'Microsoft.Authorization/policyExemptions/delete'
]

// The export is a subscription resource; the alert rules live in this resource group.
module activityLog 'activity-log.bicep' = {
  name: 'audit-activity-log'
  scope: subscription()
  params: { workspaceId: workspaceId }
}

// Only non-defaults are declared: activity log alerts are enabled by default.
// 'global' is the default, declared so a caller's azapi default_location cannot move it.
resource serviceHealth 'Microsoft.Insights/activityLogAlerts@2020-10-01' = {
  name: 'audit-service-health'
  location: 'global'
  tags: tags
  properties: {
    description: 'Azure Service Health reports an incident, maintenance, advisory or security event for this subscription.'
    scopes: [subscription().id]
    condition: { allOf: [{ field: 'category', equals: 'ServiceHealth' }] }
    actions: notify
  }
}

resource accessChanges 'Microsoft.Insights/activityLogAlerts@2020-10-01' = if (alertOnAccessChanges) {
  name: 'audit-access-changes'
  location: 'global'
  tags: tags
  properties: {
    description: 'A role assignment, policy assignment or policy exemption was created, changed or deleted.'
    scopes: [subscription().id]
    condition: {
      allOf: [
        { field: 'category', equals: 'Administrative' }
        // One alert per change, not one per Started/Accepted/Succeeded event.
        { field: 'status', equals: 'Succeeded' }
        { anyOf: [for operation in accessOperations: { field: 'operationName', equals: operation }] }
      ]
    }
    actions: notify
  }
}

output activityLogSettingId string = activityLog.outputs.id
