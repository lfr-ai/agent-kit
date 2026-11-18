using '../main.bicep'
import { requireBackendUrl, requireTokenValidation, requireWorkspace } from '../main.bicep'

param location = 'westeurope'
param name = 'sample-apim-prod'
param stage = 'prod'
param publisherEmail = 'platform@example.com'
// Synthetic IDs: compile-only fixture, not real resources.
// Guards evaluate the production policy offline, before any deployment.
param backendUrl = requireBackendUrl('https://sample-app.example.com')
param entraAudience = 'api://sample-backend'
param entraTenantId = requireTokenValidation(stage, '00000000-0000-0000-0000-000000000000', entraAudience)
param logAnalyticsWorkspaceId = requireWorkspace(
  stage,
  '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/monitoring/providers/Microsoft.OperationalInsights/workspaces/example'
)
