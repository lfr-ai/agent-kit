using '../main.bicep'

param location = 'westeurope'
param name = 'sample-apim-dev'
param stage = 'dev'
param publisherEmail = 'platform@example.com'
// Synthetic backend: compile-only fixture, not a real endpoint.
param backendUrl = 'https://sample-app.example.com'
