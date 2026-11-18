targetScope = 'resourceGroup'

@description('Label echoed back by the deployment.')
param label string = 'fixture'

@description('The label that was deployed.')
output echoed string = label
