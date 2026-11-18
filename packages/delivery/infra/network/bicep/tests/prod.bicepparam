using '../main.bicep'
import { requireAddressPrefix, requireEgress, requirePrivateDnsZones } from '../main.bicep'

param location = 'westeurope'
param name = 'sample-prod-vnet'
param stage = 'prod'
// Guards evaluate the shared input policy offline, before any deployment.
param addressPrefix = requireAddressPrefix('10.30.0.0/24')
param privateDnsZones = requirePrivateDnsZones(['keyVault', 'containerRegistry', 'containerApps'])
// Explicit cost decision; the prod default is also natGateway.
param egress = requireEgress({ mode: 'natGateway' })
