using '../main.bicep'

param location = 'westeurope'
param name = 'sampledevtfstate'
param stage = 'dev'
// Synthetic object ID: compile-only fixture, not a real identity.
param principalId = '00000000-0000-0000-0000-000000000000'
