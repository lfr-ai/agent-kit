@sealed()
type Container = {
  @description('Container name, unique within the database.')
  @minLength(1)
  @maxLength(255)
  name: string
  @description('Partition key path, for example /tenantId. It cannot be changed after creation.')
  @minLength(2)
  partitionKeyPath: string
}

@sealed()
type Database = {
  @description('Database name, unique within the account.')
  @minLength(1)
  @maxLength(255)
  name: string
  @description('Containers created in the database; omitted or empty creates none.')
  containers: Container[]?
}

@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.documents.azure.com private DNS zone ARM ID, already linked to the VNet.')
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
// The zone checks are intentionally restricted to Azure public cloud, matching Terraform.
@export()
func requirePrivateEndpoint(stage string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require privateEndpoint: an existing subnet and privatelink.documents.azure.com zone.')
        : network
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && matchesId(
          network!.privateDnsZoneId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.documents.azure.com'
        )
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and a privatelink.documents.azure.com private DNS zone ARM ID.')

// Cosmos DB treats an empty IP rule list as open to all networks, so the opt-in needs one.
@export()
func requirePublicAccess(stage string, hasPrivateEndpoint bool, allow bool, ranges string[]) string[] =>
  allow && (hasPrivateEndpoint || contains(['staging', 'prod'], stage))
    ? fail('allowPublicNetworkAccess is only for dev or test without privateEndpoint.')
    : !allow && !empty(ranges)
        ? fail('allowedIpRanges needs allowPublicNetworkAccess.')
        : allow && empty(ranges)
            ? fail('allowPublicNetworkAccess needs allowedIpRanges: Cosmos DB treats an empty list as all networks.')
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

@description('Azure region for the account and its optional private endpoint.')
@minLength(1)
param location string

@description('Globally unique account name: lowercase letters, digits and hyphens; also prefixes the private endpoint. Use a distinct name per stage.')
@minLength(3)
@maxLength(44)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Optional NoSQL database and its containers; omitted creates neither.')
param database Database?

@description('Production autoscale maximum RU/s shared by the database; serverless dev/test accounts ignore it.')
@minValue(1000)
param autoscaleMaxThroughput int = 1000

@description('Object (principal) ID of an existing identity to get Cosmos DB Built-in Data Contributor on the account, not its client ID; omitted grants nobody.')
@minLength(36)
@maxLength(36)
param principalId string?

@description('Private networking for the NoSQL (Sql) endpoint; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint, allowing only allowedIpRanges.')
param allowPublicNetworkAccess bool = false

@description('IPv4 addresses or CIDR ranges the firewall allows; at least one is needed with allowPublicNetworkAccess.')
param allowedIpRanges string[] = []

@description('Existing Log Analytics workspace ARM ID for request logs and metrics; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var network = requirePrivateEndpoint(stage, privateEndpoint)
var ipRanges = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess, allowedIpRanges)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }
// ARM evaluates names of skipped resources, so an absent database keeps a placeholder.
var databaseName = database.?name ?? 'none'
var containers = database.?containers ?? []
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

// Only non-defaults are declared. The default kind, GlobalDocumentDB, is the NoSQL API.
// Local (key) authentication is disabled. The template reference documents TLS 1.0 as the
// unset minimum, so TLS 1.2 is declared. Dev/test/staging are serverless; production is
// provisioned, zone redundant and continuously backed up instead of the periodic default.
// Public network access is disabled unless a dev or test caller opts in to an IP allow list.
resource account 'Microsoft.DocumentDB/databaseAccounts@2025-10-15' = {
  name: name
  location: location
  tags: tags
  properties: union(
    {
      databaseAccountOfferType: 'Standard'
      locations: [
        union({ locationName: location, failoverPriority: 0 }, stage == 'prod' ? { isZoneRedundant: true } : {})
      ]
      disableLocalAuth: true
      minimalTlsVersion: 'Tls12'
    },
    allowPublicNetworkAccess
      ? { ipRules: map(ipRanges, value => { ipAddressOrRange: value }) }
      : { publicNetworkAccess: 'Disabled' },
    stage == 'prod'
      ? { backupPolicy: { type: 'Continuous', continuousModeProperties: { tier: 'Continuous30Days' } } }
      : { capabilities: [{ name: 'EnableServerless' }] }
  )
}

// Production shares autoscale throughput across the database's containers;
// serverless accounts reject any throughput option.
resource sqlDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2025-10-15' = if (database != null) {
  parent: account
  name: databaseName
  properties: union(
    { resource: { id: databaseName } },
    stage == 'prod' ? { options: { autoscaleSettings: { maxThroughput: autoscaleMaxThroughput } } } : {}
  )
}

// Version 2 (large) partition keys hash the whole key value; version 1 is the default.
resource sqlContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15' = [
  for container in containers: {
    parent: sqlDatabase
    name: container.name
    properties: {
      resource: {
        id: container.name
        partitionKey: { paths: [container.partitionKeyPath], version: 2 }
      }
    }
  }
]

// A Cosmos DB data-plane role assignment, not an Azure RBAC role assignment.
resource dataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-10-15' = if (principalId != null) {
  parent: account
  name: guid(account.id, principalId ?? '', dataContributorRoleId)
  properties: {
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    principalId: principalId!
    scope: account.id
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
          groupIds: ['Sql']
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
      { name: 'cosmos-db', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

// Resource-specific tables are Microsoft's recommended destination for Cosmos DB logs.
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'cosmos-db-diagnostics'
  scope: account
  properties: {
    workspaceId: workspaceId!
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      { category: 'DataPlaneRequests', enabled: true }
      { category: 'ControlPlaneRequests', enabled: true }
    ]
    metrics: [
      { category: 'Requests', enabled: true }
    ]
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: account
  properties: { level: 'CanNotDelete' }
}

output accountId string = account.id
output documentEndpoint string = account.properties.documentEndpoint
output databaseName string? = database.?name
output containerNames string[] = map(containers, container => container.name)
