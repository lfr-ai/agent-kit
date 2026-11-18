using '../main.bicep'
import { requirePrivateEndpoint, requireReplicas, requireWorkspace } from '../main.bicep'

param location = 'westeurope'
param name = 'sample-prod-search'
param stage = 'prod'
// Synthetic IDs: compile-only fixture, not real resources.
param principalId = '00000000-0000-0000-0000-000000000000'
param indexingPrincipalId = '11111111-1111-1111-1111-111111111111'
// Guards evaluate the production policy offline, before any deployment.
param replicaCount = requireReplicas(stage, 3)
param privateEndpoint = requirePrivateEndpoint(stage, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/search'
  privateDnsZoneId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.search.windows.net'
})
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
