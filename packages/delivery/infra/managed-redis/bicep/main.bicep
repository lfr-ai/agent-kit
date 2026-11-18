@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.redis.azure.net private DNS zone ARM ID, already linked to the VNet.')
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

// ARM startsWith() ignores case; comparing take() keeps parity with Terraform's case-sensitive regex.
func isManagedRedisSku(sku string) bool =>
  !empty(filter(
    ['Balanced_B', 'MemoryOptimized_M', 'ComputeOptimized_X', 'FlashOptimized_A'],
    family =>
      take(sku, length(family)) == family && length(sku) > length(family) && onlyChars(
        skip(sku, length(family)),
        '0123456789'
      )
  ))

// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireName(value string) string =>
  length(value) >= 2 && length(value) <= 32 && contains('abcdefghijklmnopqrstuvwxyz', first(value)) && contains(
      'abcdefghijklmnopqrstuvwxyz0123456789',
      last(value)
    ) && onlyChars(value, 'abcdefghijklmnopqrstuvwxyz0123456789-') && !contains(value, '--')
    ? value
    : fail('name must use 2-32 lowercase letters, digits or single hyphens; start with a letter and end alphanumeric.')

@export()
func requirePrincipalId(value string) string =>
  map(split(value, '-'), part => length(part)) == [8, 4, 4, 4, 12] && onlyChars(value, '0123456789abcdefABCDEF-')
    ? value
    : fail('principalId must be the object (principal) ID GUID of the existing app identity.')

@export()
func requireSku(stage string, sku string) string =>
  !isManagedRedisSku(sku)
    ? fail('sku must be an Azure Managed Redis SKU, for example Balanced_B0 or MemoryOptimized_M10.')
    : stage == 'prod' && contains(['Balanced_B0', 'Balanced_B1'], sku)
        ? fail('Production rejects the dev/test sizes Balanced_B0 and Balanced_B1; choose Balanced_B3 or larger.')
        : sku

@export()
func requirePrivateEndpoint(stage string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? !contains(['staging', 'prod'], stage)
        ? network
        : fail('Staging and production require privateEndpoint: an existing subnet and privatelink.redis.azure.net zone.')
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && matchesId(
          network!.privateDnsZoneId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.redis.azure.net'
        )
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and a privatelink.redis.azure.net private DNS zone ARM ID.')

@export()
func requirePublicAccess(stage string, hasPrivateEndpoint bool, allow bool) bool =>
  allow && (hasPrivateEndpoint || contains(['staging', 'prod'], stage))
    ? fail('allowPublicNetworkAccess is only for dev or test without privateEndpoint.')
    : allow

@export()
func requireWorkspace(stage string, workspaceId string?) string? =>
  workspaceId == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for diagnostics.')
        : workspaceId
    : matchesId(workspaceId!, '/subscriptions/*/resourceGroups/*/providers/Microsoft.OperationalInsights/workspaces/*')
        ? workspaceId
        : fail('logAnalyticsWorkspaceId must be a Log Analytics workspace ARM ID.')

@description('Azure region for the cache and its optional private endpoint.')
@minLength(1)
param location string

@description('Cache name; also prefixes the private endpoint. Use a distinct name per stage.')
@minLength(2)
@maxLength(32)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Object (principal) ID of the existing app managed identity that receives data access.')
param principalId string

@description('Azure Managed Redis SKU. Production rejects Balanced_B0 and Balanced_B1.')
param sku string = 'Balanced_B0'

@description('Private networking; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint. Azure Managed Redis has no IP firewall; Entra ID still guards data access.')
param allowPublicNetworkAccess bool = false

@description('Existing Log Analytics workspace ARM ID for metrics and connection logs; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var checkedName = requireName(name)
var checkedSku = requireSku(stage, sku)
var objectId = requirePrincipalId(principalId)
var network = requirePrivateEndpoint(stage, privateEndpoint)
var publicAccess = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }

// Only non-defaults are declared: Entra ID auth, TLS 1.2, encrypted client protocol,
// port 10000 and high availability are platform defaults. Access keys are disabled
// explicitly on the database, so Entra ID is the only data-plane credential.
resource cluster 'Microsoft.Cache/redisEnterprise@2025-07-01' = {
  name: checkedName
  location: location
  tags: tags
  sku: { name: checkedSku }
  properties: {
    // Required by this API version; public only on an explicit dev or test opt-in.
    publicNetworkAccess: publicAccess ? 'Enabled' : 'Disabled'
  }
}

// EnterpriseCluster exposes one endpoint for non-cluster-aware clients (redis-py Redis).
resource database 'Microsoft.Cache/redisEnterprise/databases@2025-07-01' = {
  parent: cluster
  name: 'default'
  properties: {
    clusteringPolicy: 'EnterpriseCluster'
    accessKeysAuthentication: 'Disabled'
  }
}

resource access 'Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments@2025-07-01' = {
  parent: database
  name: replace(objectId, '-', '')
  properties: {
    accessPolicyName: 'default'
    user: { objectId: objectId }
  }
}

resource endpoint 'Microsoft.Network/privateEndpoints@2025-01-01' = if (network != null) {
  name: '${checkedName}-pe'
  location: location
  tags: tags
  properties: {
    subnet: { id: network!.subnetId }
    privateLinkServiceConnections: [
      {
        name: checkedName
        properties: {
          privateLinkServiceId: cluster.id
          groupIds: ['redisEnterprise']
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
      { name: 'redis', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

// Platform metrics are exported by the cluster; resource logs by the database.
resource clusterDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'redis-metrics'
  scope: cluster
  properties: {
    workspaceId: workspaceId!
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

resource databaseDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'redis-connection-logs'
  scope: database
  properties: {
    workspaceId: workspaceId!
    logs: [
      { category: 'ConnectionEvents', enabled: true }
    ]
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: cluster
  properties: { level: 'CanNotDelete' }
}

output redisResourceId string = cluster.id
output hostName string = cluster.properties.hostName
output port int = database.properties.port
