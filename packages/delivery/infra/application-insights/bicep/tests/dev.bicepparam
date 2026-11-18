using '../main.bicep'

param location = 'westeurope'
param name = 'sample-dev'
param stage = 'dev'
// Synthetic IDs: compile-only fixture, not real resources.
param logAnalyticsWorkspaceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
param principalId = '00000000-0000-0000-0000-000000000000'
