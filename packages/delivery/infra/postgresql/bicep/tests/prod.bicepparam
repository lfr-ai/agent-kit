using '../main.bicep'
import { requirePrivateEndpoint, requireSku, requireWorkspace } from '../main.bicep'

param location = 'westeurope'
param name = 'sample-prod-pg'
param stage = 'prod'
// Synthetic IDs: compile-only fixture, not real resources.
param administrator = {
  objectId: '00000000-0000-0000-0000-000000000000'
  name: 'sample-prod-db-admins'
  type: 'Group'
}
param databaseName = 'app'
// Guards evaluate the production policy offline, before any deployment.
param sku = requireSku(stage, { name: 'Standard_D4ds_v5', tier: 'GeneralPurpose' })
param privateEndpoint = requirePrivateEndpoint(stage, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/postgresql'
  privateDnsZoneId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com'
})
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
