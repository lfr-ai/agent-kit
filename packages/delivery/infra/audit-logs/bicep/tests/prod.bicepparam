using '../main.bicep'
import { requireActionGroupId, requireWorkspaceId } from '../main.bicep'

param stage = 'prod'
// Synthetic IDs: compile-only fixture, not real resources.
// Guards evaluate the inputs offline, before any deployment.
param logAnalyticsWorkspaceId = requireWorkspaceId('/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example')
param actionGroupId = requireActionGroupId('/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.Insights/actionGroups/sample-prod-notify')
