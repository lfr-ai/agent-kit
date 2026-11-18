type Sku = 'Standard_LRS' | 'Standard_ZRS' | 'Standard_GZRS'

@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.blob.core.windows.net private DNS zone ARM ID, already linked to the VNet.')
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
@export()
func requireSku(stage string, sku Sku) Sku =>
  contains(['staging', 'prod'], stage) && sku == 'Standard_LRS'
    ? fail('Staging and production require zone-redundant state: sku Standard_ZRS or Standard_GZRS.')
    : sku

// The zone check is intentionally restricted to Azure public cloud, matching Terraform.
@export()
func requirePrivateEndpoint(network PrivateEndpoint?) PrivateEndpoint? =>
  network == null || (matchesId(
      network!.subnetId,
      '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
    ) && matchesId(
      network!.privateDnsZoneId,
      #disable-next-line no-hardcoded-env-urls
      '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net'
    ))
    ? network
    #disable-next-line no-hardcoded-env-urls
    : fail('privateEndpoint needs a subnet ARM ID and a privatelink.blob.core.windows.net private DNS zone ARM ID.')

@export()
func requireIpRanges(hasPrivateEndpoint bool, ranges string[]) string[] =>
  hasPrivateEndpoint && !empty(ranges)
    ? fail('allowedIpRanges is only for an account without privateEndpoint, which disables public network access.')
    : empty(filter(ranges, value => !isIpRange(value)))
        ? ranges
        : fail('allowedIpRanges must hold IPv4 addresses or CIDR ranges, such as 203.0.113.0/24.')

@description('Azure region for the state storage account.')
@minLength(1)
param location string

@description('Globally unique storage account name: lowercase letters and digits. Use a distinct name per stage.')
@minLength(3)
@maxLength(24)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Object (principal) ID of the existing CI identity that reads and writes state, not its client ID.')
@minLength(36)
@maxLength(36)
param principalId string

@description('Replication. Staging and production reject Standard_LRS.')
param sku Sku = 'Standard_ZRS'

@description('Optional private endpoint for the blob endpoint; supplying it disables public network access.')
param privateEndpoint PrivateEndpoint?

@description('Public IPv4 addresses or CIDR ranges the firewall allows when there is no privateEndpoint; empty denies all public clients. Storage rejects /31 and /32: pass a bare address.')
param allowedIpRanges string[] = []

var checkedSku = requireSku(stage, sku)
var network = requirePrivateEndpoint(privateEndpoint)
var ipRanges = requireIpRanges(privateEndpoint != null, allowedIpRanges)
var tags = { stage: stage }
var blobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
// Recovery window for deleted state blobs and containers.
var softDeleteRetentionDays = 30

// Only non-defaults are declared, plus anonymous blob access pinned off. HTTPS only and
// no cross-tenant replication are defaults. Shared keys are allowed and an unset minimum
// TLS version accepts TLS 1.0 by default, so both are declared. The firewall denies
// every public client outside allowedIpRanges; a private endpoint disables public access.
resource account 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: checkedSku }
  properties: union(
    {
      allowSharedKeyAccess: false
      allowBlobPublicAccess: false
      minimumTlsVersion: 'TLS1_2'
    },
    network == null
      ? {
          networkAcls: {
            defaultAction: 'Deny'
            ipRules: map(ipRanges, value => { value: value, action: 'Allow' })
          }
        }
      : { publicNetworkAccess: 'Disabled' }
  )
}

// Every state write creates a version; deleted blobs and containers stay recoverable for
// softDeleteRetentionDays.
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-06-01' = {
  parent: account
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: { enabled: true, days: softDeleteRetentionDays }
    containerDeleteRetentionPolicy: { enabled: true, days: softDeleteRetentionDays }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-06-01' = {
  parent: blobService
  name: 'tfstate'
}

// Container scope is the least privilege the azurerm backend documents for Entra ID auth.
resource stateWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(container.id, principalId, blobDataContributorRoleId)
  scope: container
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: account
  properties: { level: 'CanNotDelete' }
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

output storageAccountResourceId string = account.id
output storageAccountName string = account.name
output containerName string = container.name
