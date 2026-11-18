using '../main.bicep'
import { requirePrivateEndpoint, requireWorkspace } from '../main.bicep'

param location = 'westeurope'
param name = 'sampleprodstorage'
param stage = 'prod'
param containers = ['uploads', 'exports']
// Synthetic IDs: compile-only fixture, not real resources.
param principalId = '00000000-0000-0000-0000-000000000000'
// Guards evaluate the production policy offline, before any deployment.
param privateEndpoint = requirePrivateEndpoint(stage, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/storage'
  privateDnsZoneId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net'
})
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
