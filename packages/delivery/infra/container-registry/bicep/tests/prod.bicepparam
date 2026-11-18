using '../main.bicep'
import { requirePrivateEndpoint, requireSku, requireWorkspace } from '../main.bicep'

param location = 'westeurope'
param name = 'sampleprodacr'
param stage = 'prod'
// Synthetic IDs: compile-only fixture, not real resources.
param pullPrincipalId = '00000000-0000-0000-0000-000000000000'
param pushPrincipalId = '11111111-1111-1111-1111-111111111111'
// Guards evaluate the production policy offline, before any deployment.
// true because privateEndpoint is supplied below; referencing that param here would
// crash Bicep 0.39 build-params whenever its own guard fails. No public access or IP rules.
param sku = requireSku(stage, 'Premium', true, false, false)
param privateEndpoint = requirePrivateEndpoint(stage, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/registry'
  privateDnsZoneId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io'
})
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
