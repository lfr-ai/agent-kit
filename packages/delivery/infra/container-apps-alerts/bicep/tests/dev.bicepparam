using '../main.bicep'

param namePrefix = 'sample-dev'
param stage = 'dev'
// Synthetic ID: compile-only fixture, not a real app.
param containerAppResourceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.App/containerApps/sample-dev'
// Dev and test need exactly one of emailReceivers, existingActionGroupResourceId or this opt-out.
param unmonitored = true
