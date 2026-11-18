using '../main.bicep'

param location = 'westeurope'
param name = 'sample-dev-cosmos'
param stage = 'dev'
param database = {
  name: 'app'
  containers: [{ name: 'items', partitionKeyPath: '/tenantId' }]
}
