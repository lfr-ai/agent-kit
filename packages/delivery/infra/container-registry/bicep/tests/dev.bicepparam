using '../main.bicep'

param location = 'westeurope'
param name = 'sampledevacr'
param stage = 'dev'
// Synthetic object ID: compile-only fixture, not a real identity.
param pullPrincipalId = '00000000-0000-0000-0000-000000000000'
// Basic cannot disable public access, so development opts in explicitly.
param allowPublicNetworkAccess = true
