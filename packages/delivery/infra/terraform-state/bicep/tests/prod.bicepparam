using '../main.bicep'
import { requireSku } from '../main.bicep'

param location = 'westeurope'
param name = 'sampleprodtfstate'
param stage = 'prod'
// Synthetic object ID: compile-only fixture, not a real identity.
param principalId = '00000000-0000-0000-0000-000000000000'
// The guard evaluates the production policy offline, before any deployment.
param sku = requireSku(stage, 'Standard_GZRS')
