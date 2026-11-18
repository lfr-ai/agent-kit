using '../main.bicep'
import { requireContainerAppId, requireEmailReceivers } from '../main.bicep'

param namePrefix = 'sample-prod'
param stage = 'prod'
// Synthetic values: compile-only fixture, not real resources or people.
param containerAppResourceId = requireContainerAppId('/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.App/containerApps/sample-prod')
// Exactly one destination is required in production; unmonitored is rejected.
param emailReceivers = requireEmailReceivers(stage, ['operations@example.com'], null, false)
