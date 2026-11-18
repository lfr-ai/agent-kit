@sealed()
type ModelDeployment = {
  @description('Deployment name that clients call.')
  name: string
  @description('Model name from the Foundry model catalog.')
  model: string
  @description('Pinned model version; availability is regional.')
  version: string
  @description('Deployment type, for example GlobalStandard or DataZoneStandard.')
  sku: string
  @description('Capacity units; for Standard types one unit is 1,000 tokens per minute.')
  capacity: int
  @description('Model publisher format; omit for OpenAI models.')
  format: string?
}

@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('The three existing Foundry private DNS zone ARM IDs, already linked to the VNet.')
  privateDnsZoneIds: string[]
}

func onlyChars(value string, alphabet string) bool =>
  empty(filter(range(0, length(value)), i => !contains(alphabet, substring(value, i, 1))))

// Each '*' segment must be non-empty; every other segment must match exactly (case-sensitive).
func matchesId(value string, pattern string) bool =>
  length(split(value, '/')) == length(split(pattern, '/'))
    ? empty(filter(
        range(0, length(split(pattern, '/'))),
        i =>
          split(pattern, '/')[i] == '*' ? empty(split(value, '/')[i]) : split(value, '/')[i] != split(pattern, '/')[i]
      ))
    : false

// Four dot-separated groups of 1-3 digits; the service checks the octet values.
func isIpv4(value string) bool =>
  onlyChars(value, '0123456789.') && length(split(value, '.')) == 4 && empty(filter(
    split(value, '.'),
    octet => empty(octet) || length(octet) > 3
  ))

// An IPv4 address, or a CIDR range with a 1-2 digit prefix length.
func isIpRange(value string) bool =>
  length(split(value, '/')) == 1
    ? isIpv4(value)
    : length(split(value, '/')) == 2 && isIpv4(split(value, '/')[0]) && isPrefixLength(split(value, '/')[1])

func isPrefixLength(value string) bool => onlyChars(value, '0123456789') && contains([1, 2], length(value))

// Exported guards are also evaluated offline by build-params in the tests.
// The zone check is intentionally restricted to Azure public cloud, matching Terraform.
@export()
func requirePrivateEndpoint(stage string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require privateEndpoint: an existing subnet and the three Foundry private DNS zones.')
        : network
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && empty(filter(
          network!.privateDnsZoneIds,
          id => !matchesId(id, '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/*')
        )) && sort(map(network!.privateDnsZoneIds, id => last(split(id, '/'))), (a, b) => a < b) == [
          'privatelink.cognitiveservices.azure.com'
          'privatelink.openai.azure.com'
          'privatelink.services.ai.azure.com'
        ]
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and the privatelink.cognitiveservices.azure.com, privatelink.openai.azure.com and privatelink.services.ai.azure.com private DNS zone ARM IDs.')

@export()
func requirePublicAccess(stage string, hasPrivateEndpoint bool, allow bool, ranges string[]) string[] =>
  allow && (hasPrivateEndpoint || contains(['staging', 'prod'], stage))
    ? fail('allowPublicNetworkAccess is only for dev or test without privateEndpoint.')
    : !allow && !empty(ranges)
        ? fail('allowedIpRanges needs allowPublicNetworkAccess.')
        : empty(filter(ranges, value => !isIpRange(value)))
            ? ranges
            : fail('allowedIpRanges must hold IPv4 addresses or CIDR ranges, such as 203.0.113.0/24.')

@export()
func requireAllClients(allowPublic bool, ranges string[], allowAll bool) string =>
  !allowAll
    ? 'Deny'
    : allowPublic && empty(ranges)
        ? 'Allow'
        : fail('allowAllPublicClients needs allowPublicNetworkAccess and no allowedIpRanges.')

@export()
func requireWorkspace(stage string, workspaceId string?) string? =>
  workspaceId == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for diagnostics.')
        : workspaceId
    : empty(workspaceId!) ? fail('logAnalyticsWorkspaceId must be omitted or non-empty.') : workspaceId

@description('Azure region for the Foundry resource, its project and the optional private endpoint.')
@minLength(1)
param location string

@description('Globally unique name; also the custom subdomain and the project name.')
@minLength(2)
@maxLength(64)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Object (principal) ID of the existing app identity that calls the models.')
param principalId string

@description('Model deployments; none by default. Model, version and quota are regional.')
param deployments ModelDeployment[] = []

@description('Private networking; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint, denying all but allowedIpRanges.')
param allowPublicNetworkAccess bool = false

@description('IPv4 addresses or CIDR ranges the network ACL allows with allowPublicNetworkAccess.')
param allowedIpRanges string[] = []

@description('With allowPublicNetworkAccess and no allowedIpRanges: allow every client network. Local keys stay disabled, so callers still need Entra tokens and a role. For dev callers without fixed egress, such as Container Apps outside a virtual network.')
param allowAllPublicClients bool = false

@description('Existing Log Analytics workspace ARM ID for resource logs and metrics; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var network = requirePrivateEndpoint(stage, privateEndpoint)
var ipRanges = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess, allowedIpRanges)
var aclDefault = requireAllClients(allowPublicNetworkAccess, ipRanges, allowAllPublicClients)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }
// Built-in role definition names are the same in every tenant.
var openAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var foundryUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

// Public access is disabled unless a dev or test caller opts in to a deny-by-default
// network ACL with an IP allow list.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-09-01' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: union(
    {
      allowProjectManagement: true
      customSubDomainName: name
      disableLocalAuth: true
      publicNetworkAccess: allowPublicNetworkAccess ? 'Enabled' : 'Disabled'
    },
    allowPublicNetworkAccess
      ? { networkAcls: { defaultAction: aclDefault, ipRules: map(ipRanges, value => { value: value }) } }
      : {}
  )
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-09-01' = {
  parent: foundry
  name: name
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {}
}

// The account accepts one child operation at a time, so deployments run serially.
@batchSize(1)
resource modelDeployments 'Microsoft.CognitiveServices/accounts/deployments@2025-09-01' = [
  for deployment in deployments: {
    parent: foundry
    name: deployment.name
    sku: { name: deployment.sku, capacity: deployment.capacity }
    properties: {
      model: { format: deployment.?format ?? 'OpenAI', name: deployment.model, version: deployment.version }
    }
    dependsOn: [project]
  }
]

// OpenAI-compatible inference on the account; no key listing or management rights.
resource inferenceAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, principalId, openAiUser)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUser)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Microsoft's recommended role for the project endpoint (Foundry SDK, agents, responses).
resource projectAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, principalId, foundryUser)
  scope: project
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUser)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Binding before the account finishes provisioning fails with AccountProvisioningStateInvalid.
resource endpoint 'Microsoft.Network/privateEndpoints@2025-01-01' = if (network != null) {
  name: '${name}-pe'
  location: location
  tags: tags
  properties: {
    subnet: { id: network!.subnetId }
    privateLinkServiceConnections: [
      {
        name: name
        properties: {
          privateLinkServiceId: foundry.id
          groupIds: ['account']
        }
      }
    ]
  }
  dependsOn: [project, modelDeployments]
}

resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01' = if (network != null) {
  parent: endpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: map(network!.privateDnsZoneIds, id => {
      name: last(split(id, '/'))
      properties: { privateDnsZoneId: id }
    })
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'foundry-logs'
  scope: foundry
  properties: {
    workspaceId: workspaceId!
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

// Resource-scoped: inherited by the project and deployments, never by unrelated resources.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: foundry
  properties: { level: 'CanNotDelete' }
}

output foundryResourceId string = foundry.id
output projectResourceId string = project.id
@description('OpenAI-compatible v1 base URL; request Entra tokens for https://ai.azure.com/.default.')
output openAiEndpoint string = 'https://${name}.openai.azure.com/openai/v1/'
@description('Foundry project endpoint for the Foundry SDK.')
output projectEndpoint string = 'https://${name}.services.ai.azure.com/api/projects/${name}'
