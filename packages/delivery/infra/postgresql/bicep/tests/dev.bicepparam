using '../main.bicep'

param location = 'westeurope'
param name = 'sample-dev-pg'
param stage = 'dev'
// Synthetic object ID: compile-only fixture, not a real identity.
param administrator = {
  objectId: '00000000-0000-0000-0000-000000000000'
  name: 'sample-dev-db-admins'
  type: 'Group'
}
param databaseName = 'app'
