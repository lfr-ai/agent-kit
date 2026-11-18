using '../main.bicep'
import { requirePrivateEndpoint, requireWorkspace } from '../main.bicep'

param location = 'swedencentral'
param name = 'sample-foundry-prod'
param stage = 'prod'
// Synthetic IDs: compile-only fixture, not real resources.
param principalId = '00000000-0000-0000-0000-000000000000'
param deployments = []
// Guards evaluate the production policy offline, before any deployment.
param privateEndpoint = requirePrivateEndpoint(stage, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/foundry'
  privateDnsZoneIds: [
    '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com'
    '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com'
    '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.services.ai.azure.com'
  ]
})
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
