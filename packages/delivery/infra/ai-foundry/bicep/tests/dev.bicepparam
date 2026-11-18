using '../main.bicep'

param location = 'swedencentral'
param name = 'sample-foundry-dev'
param stage = 'dev'
// Synthetic object ID: compile-only fixture, not a real identity.
param principalId = '00000000-0000-0000-0000-000000000000'
// Current example only; check regional availability and quota before use.
param deployments = [
  {
    name: 'gpt-5.4-mini'
    model: 'gpt-5.4-mini'
    version: '2026-03-17'
    sku: 'GlobalStandard'
    capacity: 10
  }
]
