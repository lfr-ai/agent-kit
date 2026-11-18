using '../main.bicep'
import { requirePrincipalId, requireWorkspaceId } from '../main.bicep'

param location = 'westeurope'
param name = 'sample-prod'
param stage = 'prod'
// Synthetic IDs: compile-only fixture, not real resources.
// Guards evaluate the inputs offline, before any deployment.
param logAnalyticsWorkspaceId = requireWorkspaceId('/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example')
param principalId = requirePrincipalId('00000000-0000-0000-0000-000000000000')
