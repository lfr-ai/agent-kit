@sealed()
type EntraAdministrator = {
  @description('Object (principal) ID of the existing Entra user, group or service principal.')
  @minLength(36)
  @maxLength(36)
  objectId: string
  @description('Its Entra display name; for a managed identity, the identity name.')
  @minLength(1)
  name: string
  type: 'User' | 'Group' | 'ServicePrincipal'
}

@sealed()
type Sku = {
  @description('Compute size, for example Standard_B2s or Standard_D4ds_v5.')
  name: string
  tier: 'Burstable' | 'GeneralPurpose' | 'MemoryOptimized'
}

@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.postgres.database.azure.com private DNS zone ARM ID, already linked to the VNet.')
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
// Burstable stays allowed in staging: zone-redundant HA is a production cost choice.
@export()
func requireSku(stage string, sku Sku) Sku =>
  stage == 'prod' && sku.tier == 'Burstable'
    ? fail('Production needs a GeneralPurpose or MemoryOptimized sku; Burstable has no zone-redundant high availability.')
    : sku

// The zone check is intentionally restricted to Azure public cloud, matching Terraform.
@export()
func requirePrivateEndpoint(stage string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require privateEndpoint: an existing subnet and privatelink.postgres.database.azure.com zone.')
        : network
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && matchesId(
          network!.privateDnsZoneId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com'
        )
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and a privatelink.postgres.database.azure.com private DNS zone ARM ID.')

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

@description('Azure region for the server and its optional private endpoint.')
@minLength(1)
param location string

@description('Globally unique server name; also prefixes the private endpoint. Use a distinct name per stage.')
@minLength(3)
@maxLength(63)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Existing Entra principal that administers the server and creates database roles.')
param administrator EntraAdministrator

@description('Application database created on the server.')
@minLength(1)
@maxLength(63)
param databaseName string

@description('Compute size; defaults to Standard_B1ms (Burstable) in dev/test and Standard_D2ds_v5 (GeneralPurpose) in production.')
param sku Sku?

@description('Initial Premium SSD storage in GiB; 32 is the smallest size. Autogrow raises it online, and storage can never shrink.')
@minValue(32)
param storageSizeGB int = 32

@description('Private networking; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint, with firewall rules for allowedIpRanges only.')
param allowPublicNetworkAccess bool = false

@description('IPv4 addresses or CIDR ranges that get a firewall rule with allowPublicNetworkAccess.')
param allowedIpRanges string[] = []

@description('Existing Log Analytics workspace ARM ID for server logs and metrics; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

@description('Extensions to allowlist in azure.extensions, for example vector or age; empty allows none.')
param extensions string[] = []

var defaultSku = stage == 'prod'
  ? { name: 'Standard_D2ds_v5', tier: 'GeneralPurpose' }
  : { name: 'Standard_B1ms', tier: 'Burstable' }
var compute = requireSku(stage, sku ?? defaultSku)
var network = requirePrivateEndpoint(stage, privateEndpoint)
var ipRanges = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess, allowedIpRanges)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }

// Only non-defaults are declared. Password authentication is on by default, so it is
// switched off explicitly. Storage has no documented default size; autogrow avoids a
// read-only server when the disk fills. Geo-redundant backup can only be chosen at creation.
// Public access is disabled unless a dev or test caller opts in; with no firewall rule
// the public endpoint still denies every client.
resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01' = {
  name: name
  location: location
  tags: tags
  sku: compute
  properties: union(
    {
      version: '18'
      authConfig: {
        activeDirectoryAuth: 'Enabled'
        passwordAuth: 'Disabled'
        tenantId: tenant().tenantId
      }
      storage: { storageSizeGB: storageSizeGB, autoGrow: 'Enabled' }
      network: { publicNetworkAccess: allowPublicNetworkAccess ? 'Enabled' : 'Disabled' }
    },
    stage == 'prod'
      ? {
          highAvailability: { mode: 'ZoneRedundant' }
          backup: { geoRedundantBackup: 'Enabled' }
        }
      : {}
  )
}

resource entraAdmin 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2025-08-01' = {
  parent: server
  name: administrator.objectId
  properties: {
    principalName: administrator.name
    principalType: administrator.type
    tenantId: tenant().tenantId
  }
}

// Server operations run one after another: parallel changes to one server can conflict.
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2025-08-01' = {
  parent: server
  name: databaseName
  dependsOn: [entraAdmin]
}

// A dynamic parameter: no restart. Each database still runs CREATE EXTENSION.
resource allowedExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01' = if (!empty(extensions)) {
  parent: server
  name: 'azure.extensions'
  properties: {
    value: join(extensions, ',')
    source: 'user-override'
  }
  dependsOn: [database]
}

// Only with the explicit dev/test opt-in; rules run one at a time like other server operations.
@batchSize(1)
resource firewallRules 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2025-08-01' = [
  for value in ipRanges: {
    parent: server
    name: 'allow-${replace(replace(value, '.', '-'), '/', '-')}'
    properties: {
      startIpAddress: parseCidr(contains(value, '/') ? value : '${value}/32').network
      endIpAddress: parseCidr(contains(value, '/') ? value : '${value}/32').broadcast
    }
    dependsOn: [allowedExtensions]
  }
]

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
          privateLinkServiceId: server.id
          groupIds: ['postgresqlServer']
        }
      }
    ]
  }
  dependsOn: [database, allowedExtensions]
}

resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-01-01' = if (network != null) {
  parent: endpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'postgresql', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'postgresql-diagnostics'
  scope: server
  properties: {
    workspaceId: workspaceId!
    logs: [
      { category: 'PostgreSQLLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: server
  properties: { level: 'CanNotDelete' }
}

output serverId string = server.id
output fqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
