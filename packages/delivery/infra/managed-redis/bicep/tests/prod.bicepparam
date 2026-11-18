using '../main.bicep'
import { requirePrivateEndpoint, requireSku, requireWorkspace } from '../main.bicep'

param location = 'westeurope'
param name = 'sample-prod'
param stage = 'prod'
// Synthetic IDs: compile-only fixture, not real resources.
param principalId = '00000000-0000-0000-0000-000000000000'
// Guards evaluate the production policy offline, before any deployment.
param sku = requireSku(stage, 'Balanced_B3')
param privateEndpoint = requirePrivateEndpoint(stage, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/redis'
  privateDnsZoneId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.redis.azure.net'
})
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
