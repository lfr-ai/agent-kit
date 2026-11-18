using '../main.bicep'
import { requireDigest } from '../app.bicep'
import { requireAvailability, requirePrivateEndpoint } from '../environment.bicep'

param location = 'westeurope'
param appName = 'sample-prod'
param environmentName = 'sample-prod-env'
param stage = 'prod'
// Synthetic digest and IDs: compile-only fixture, not a runnable image or real resources.
param containerImage = requireDigest('example.azurecr.io/sample@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
// Guards evaluate the production policy offline, before any deployment.
param availability = requireAvailability(stage, {
  minReplicas: 2
  maxReplicas: 10
  zoneRedundant: true
  deletionProtection: true
  infrastructureSubnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/apps'
})
param privateEndpoint = requirePrivateEndpoint(stage, location, {
  subnetId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/virtualNetworks/example/subnets/endpoints'
  privateDnsZoneId: '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/network/providers/Microsoft.Network/privateDnsZones/privatelink.westeurope.azurecontainerapps.io'
})
