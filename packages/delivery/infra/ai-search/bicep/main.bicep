@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.search.windows.net private DNS zone ARM ID, already linked to the VNet.')
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

// The production replica floor for the read SLA; also the production default.
func productionMinReplicas() int => 2

// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireReplicas(stage string, replicaCount int?) int? =>
  stage == 'prod' && (replicaCount ?? productionMinReplicas()) < productionMinReplicas()
    ? fail('Production needs replicaCount 2 or more for the read SLA; use 3 for read-write.')
    : replicaCount

// The zone check is intentionally restricted to Azure public cloud, matching Terraform.
@export()
func requirePrivateEndpoint(stage string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require privateEndpoint: an existing subnet and privatelink.search.windows.net zone.')
        : network
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && matchesId(
          network!.privateDnsZoneId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.search.windows.net'
        )
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and a privatelink.search.windows.net private DNS zone ARM ID.')

// Azure AI Search treats an empty IP rule list as open to all networks, so the opt-in needs one.
@export()
func requirePublicAccess(stage string, hasPrivateEndpoint bool, allow bool, ranges string[]) string[] =>
  allow && (hasPrivateEndpoint || contains(['staging', 'prod'], stage))
    ? fail('allowPublicNetworkAccess is only for dev or test without privateEndpoint.')
    : !allow && !empty(ranges)
        ? fail('allowedIpRanges needs allowPublicNetworkAccess.')
        : allow && empty(ranges)
            ? fail('allowPublicNetworkAccess needs allowedIpRanges: Azure AI Search treats an empty list as all networks.')
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

@description('Azure region for the search service and its optional private endpoint.')
@minLength(1)
param location string

@description('Globally unique search service name; also prefixes the private endpoint. Use a distinct name per stage.')
@minLength(2)
@maxLength(60)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Object (principal) ID of the existing app identity that queries indexes, not its client ID.')
@minLength(36)
@maxLength(36)
param principalId string

@description('Optional object (principal) ID of an existing workload identity that loads documents into indexes.')
@minLength(36)
@maxLength(36)
param indexingPrincipalId string?

@description('Replicas; production defaults to 2 for the read SLA. Use 3 for read-write; Basic allows at most 3.')
@minValue(1)
@maxValue(12)
param replicaCount int?

@description('Private networking; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint, allowing only allowedIpRanges.')
param allowPublicNetworkAccess bool = false

@description('IPv4 addresses or CIDR ranges the search firewall allows; at least one is needed with allowPublicNetworkAccess.')
param allowedIpRanges string[] = []

@description('Existing Log Analytics workspace ARM ID for operation logs and metrics; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var replicas = requireReplicas(stage, replicaCount ?? (stage == 'prod' ? productionMinReplicas() : null))
var network = requirePrivateEndpoint(stage, privateEndpoint)
var ipRanges = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess, allowedIpRanges)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }
var indexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var indexDataContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'

// Only non-defaults are declared: API keys are allowed by default, so they are disabled.
// Semantic ranker starts on the free plan; production opts in to the billed standard
// plan so queries keep working after the monthly free allowance. Two or more replicas
// spread across availability zones where the region has them. Public access is
// disabled unless a dev or test caller opts in to an IP allow list.
resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: stage == 'prod' ? 'standard' : 'basic' }
  properties: union(
    { disableLocalAuth: true },
    replicas == null ? {} : { replicaCount: replicas },
    stage == 'prod' ? { semanticSearch: 'standard' } : {},
    allowPublicNetworkAccess
      ? { networkRuleSet: { ipRules: map(ipRanges, value => { value: value }) } }
      : { publicNetworkAccess: 'Disabled' }
  )
}

resource indexReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, principalId, indexDataReaderRoleId)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', indexDataReaderRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource indexContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (indexingPrincipalId != null) {
  name: guid(search.id, indexingPrincipalId ?? '', indexDataContributorRoleId)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', indexDataContributorRoleId)
    principalId: indexingPrincipalId!
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
          privateLinkServiceId: search.id
          groupIds: ['searchService']
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
      { name: 'search', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'search-diagnostics'
  scope: search
  properties: {
    workspaceId: workspaceId!
    logs: [
      { category: 'OperationLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: search
  properties: { level: 'CanNotDelete' }
}

output searchServiceId string = search.id
output endpoint string = search.properties.endpoint
