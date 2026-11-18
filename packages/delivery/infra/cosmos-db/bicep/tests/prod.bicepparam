using '../main.bicep'
import { requirePrivateEndpoint, requireWorkspace } from '../main.bicep'

param location = 'westeurope'
param name = 'sample-prod-cosmos'
param stage = 'prod'
param database = {
  name: 'app'
  containers: [
    { name: 'items', partitionKeyPath: '/tenantId' }
    { name: 'events', partitionKeyPath: '/streamId' }
  ]
}
param autoscaleMaxThroughput = 4000
// Synthetic IDs: compile-only fixture, not real resources.
param principalId = '00000000-0000-0000-0000-000000000000'
// Guards evaluate the production policy offline, before any deployment.
param privateEndpoint = requirePrivateEndpoint(stage, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/cosmos-db'
  privateDnsZoneId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.documents.azure.com'
})
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
