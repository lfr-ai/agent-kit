targetScope = 'subscription'

param workspaceId string

// Recommendation (Advisor) and Autoscale (classic autoscale settings) are left out.
var categories = ['Administrative', 'Security', 'Policy', 'Alert', 'ServiceHealth', 'ResourceHealth']

resource export 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'audit-activity-log'
  properties: {
    workspaceId: workspaceId
    logs: [for category in categories: { category: category, enabled: true }]
  }
}

output id string = export.id
