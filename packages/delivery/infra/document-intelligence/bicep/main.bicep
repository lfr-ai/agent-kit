@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.cognitiveservices.azure.com private DNS zone ARM ID, already linked to the VNet.')
  privateDnsZoneId: string
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
        ? fail('Staging and production require privateEndpoint: an existing subnet and privatelink.cognitiveservices.azure.com zone.')
        : network
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && matchesId(
          network!.privateDnsZoneId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com'
        )
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and a privatelink.cognitiveservices.azure.com private DNS zone ARM ID.')

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
func requireWorkspace(stage string, workspaceId string?) string? =>
  workspaceId == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for diagnostics.')
        : workspaceId
    : empty(workspaceId!) ? fail('logAnalyticsWorkspaceId must be omitted or non-empty.') : workspaceId

@description('Azure region for the resource and its optional private endpoint.')
@minLength(1)
param location string

@description('Globally unique name; also the custom subdomain that Entra ID authentication needs.')
@minLength(2)
@maxLength(64)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Object (principal) ID of the existing app identity that analyzes documents.')
param principalId string

@description('Private networking; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint, denying all but allowedIpRanges.')
param allowPublicNetworkAccess bool = false

@description('IPv4 addresses or CIDR ranges the network ACL allows with allowPublicNetworkAccess.')
param allowedIpRanges string[] = []

@description('Existing Log Analytics workspace ARM ID for resource logs and metrics; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var network = requirePrivateEndpoint(stage, privateEndpoint)
var ipRanges = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess, allowedIpRanges)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }
// Built-in Cognitive Services User; on this single-service resource it grants Document Intelligence only.
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'

// Public access is disabled unless a dev or test caller opts in to a deny-by-default
// network ACL with an IP allow list.
resource account 'Microsoft.CognitiveServices/accounts@2025-09-01' = {
  name: name
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: { name: 'S0' }
  properties: union(
    {
      customSubDomainName: name
      disableLocalAuth: true
      publicNetworkAccess: allowPublicNetworkAccess ? 'Enabled' : 'Disabled'
    },
    allowPublicNetworkAccess
      ? { networkAcls: { defaultAction: 'Deny', ipRules: map(ipRanges, value => { value: value }) } }
      : {}
  )
}

resource analyzeAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, principalId, cognitiveServicesUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

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
          privateLinkServiceId: account.id
          groupIds: ['account']
        }
      }
    ]
  }
}

resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01' = if (network != null) {
  parent: endpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'cognitiveservices', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'document-intelligence-logs'
  scope: account
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

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: account
  properties: { level: 'CanNotDelete' }
}

output documentIntelligenceResourceId string = account.id
@description('Custom-subdomain endpoint; request Entra tokens for https://cognitiveservices.azure.com/.default.')
output endpoint string = account.properties.endpoint
