using '../main.bicep'
import { requireDigest } from '../app.bicep'
import { requireAvailability } from '../environment.bicep'

param location = 'westeurope'
param appName = 'sample-dev'
param environmentName = 'sample-dev-env'
param stage = 'dev'
// Synthetic digest: compile-only fixture, not a runnable image.
param containerImage = requireDigest('example.azurecr.io/sample@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
param availability = requireAvailability(stage, {
  minReplicas: 0
  maxReplicas: 3
  zoneRedundant: false
  deletionProtection: false
  // No infrastructureSubnetId: a dev environment without VNet integration.
})
