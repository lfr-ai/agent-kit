@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.blob.core.windows.net private DNS zone ARM ID, already linked to the VNet.')
  privateDnsZoneId: string
}

@description('Blob container name: 3-63 lowercase letters, digits or single hyphens.')
@minLength(3)
@maxLength(63)
type ContainerName = string

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
// The zone checks are intentionally restricted to Azure public cloud, matching Terraform.
@export()
func requirePrivateEndpoint(stage string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? contains(['staging', 'prod'], stage)
        #disable-next-line no-hardcoded-env-urls
        ? fail('Staging and production require privateEndpoint: an existing subnet and privatelink.blob.core.windows.net zone.')
        : network
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && matchesId(
          network!.privateDnsZoneId,
          #disable-next-line no-hardcoded-env-urls
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net'
        )
        ? network
        #disable-next-line no-hardcoded-env-urls
        : fail('privateEndpoint needs a subnet ARM ID and a privatelink.blob.core.windows.net private DNS zone ARM ID.')

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

@description('Azure region for the storage account and its optional private endpoint.')
@minLength(1)
param location string

@description('Globally unique storage account name: lowercase letters and digits; also prefixes the private endpoint. Use a distinct name per stage.')
@minLength(3)
@maxLength(24)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Object (principal) ID of the existing app identity that reads and writes blobs, not its client ID.')
@minLength(36)
@maxLength(36)
param principalId string

@description('Private blob containers to create; empty creates none.')
param containers ContainerName[] = []

@description('Private networking for the blob endpoint; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint, denying all but allowedIpRanges.')
param allowPublicNetworkAccess bool = false

@description('Public IPv4 addresses or CIDR ranges the firewall allows; needs allowPublicNetworkAccess. Storage rejects /31 and /32: pass a bare address.')
param allowedIpRanges string[] = []

@description('Existing Log Analytics workspace ARM ID for blob logs and metrics; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var network = requirePrivateEndpoint(stage, privateEndpoint)
var ipRanges = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess, allowedIpRanges)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }
var blobContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
// Production recovery window for deleted blobs and containers.
var softDeleteRetentionDays = 30

// Only non-defaults are declared, plus anonymous access pinned off. HTTPS only, the Hot
// tier and no cross-tenant replication are defaults. Shared keys are allowed and an unset
// minimum TLS version accepts TLS 1.0 by default, so both are declared. Public network
// access is disabled unless a dev or test caller opts in to an IP allow list.
resource account 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: stage == 'prod' ? 'Standard_ZRS' : 'Standard_LRS' }
  properties: union(
    {
      allowSharedKeyAccess: false
      defaultToOAuthAuthentication: true
      allowBlobPublicAccess: false
      minimumTlsVersion: 'TLS1_2'
    },
    allowPublicNetworkAccess
      ? {
          networkAcls: {
            defaultAction: 'Deny'
            ipRules: map(ipRanges, value => { value: value, action: 'Allow' })
          }
        }
      : { publicNetworkAccess: 'Disabled' }
  )
}

// Production keeps every overwrite as a version; deleted blobs and containers stay
// recoverable for softDeleteRetentionDays. Dev/test keep the platform defaults (all off).
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = {
  parent: account
  name: 'default'
  properties: stage == 'prod'
    ? {
        isVersioningEnabled: true
        deleteRetentionPolicy: { enabled: true, days: softDeleteRetentionDays }
        containerDeleteRetentionPolicy: { enabled: true, days: softDeleteRetentionDays }
      }
    : {}
}

resource blobContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = [
  for container in containers: {
    parent: blobService
    name: container
  }
]

// Narrowest owned scope: each managed container, or the account when none is managed.
resource containerBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (container, i) in containers: {
    name: guid(blobContainers[i].id, principalId, blobContributorRoleId)
    scope: blobContainers[i]
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributorRoleId)
      principalId: principalId
      principalType: 'ServicePrincipal'
    }
  }
]

resource accountBlobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (empty(containers)) {
  name: guid(account.id, principalId, blobContributorRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributorRoleId)
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
          groupIds: ['blob']
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
      { name: 'blob', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

// Blob logs exist only on the blob service, not on the account.
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'blob-diagnostics'
  scope: blobService
  properties: {
    workspaceId: workspaceId!
    logs: [
      { category: 'StorageRead', enabled: true }
      { category: 'StorageWrite', enabled: true }
      { category: 'StorageDelete', enabled: true }
    ]
    metrics: [
      { category: 'Transaction', enabled: true }
    ]
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: account
  properties: { level: 'CanNotDelete' }
}

output storageAccountId string = account.id
output blobEndpoint string = account.properties.primaryEndpoints.blob
output containerNames string[] = containers
