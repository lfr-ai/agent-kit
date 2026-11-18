using '../main.bicep'

param stage = 'dev'
// Synthetic IDs: compile-only fixture, not real resources.
param logAnalyticsWorkspaceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
param actionGroupId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.Insights/actionGroups/sample-dev-notify'
