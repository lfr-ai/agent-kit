@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.azurecr.io private DNS zone ARM ID, already linked to the VNet.')
  privateDnsZoneId: string
}

type Sku = 'Basic' | 'Standard' | 'Premium'

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
// Basic and Standard cannot disable public access or filter IPs; only Premium can.
@export()
func requireSku(stage string, sku Sku, hasPrivateEndpoint bool, allowPublic bool, hasIpRanges bool) Sku =>
  sku != 'Premium' && (contains(['staging', 'prod'], stage) || hasPrivateEndpoint)
    ? fail('Staging, production and privateEndpoint require sku Premium.')
    : sku != 'Premium' && (!allowPublic || hasIpRanges)
        ? fail('Basic and Standard need allowPublicNetworkAccess without allowedIpRanges; private access and IP rules require sku Premium.')
        : sku

// The zone check is intentionally restricted to Azure public cloud, matching Terraform.
@export()
func requirePrivateEndpoint(stage string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? contains(['staging', 'prod'], stage)
        ? fail('Staging and production require privateEndpoint: an existing subnet and privatelink.azurecr.io zone.')
        : network
    : matchesId(
          network!.subnetId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*/subnets/*'
        ) && matchesId(
          network!.privateDnsZoneId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.azurecr.io'
        )
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and a privatelink.azurecr.io private DNS zone ARM ID.')

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
        ? fail('Staging and production require logAnalyticsWorkspaceId: an existing Log Analytics workspace for audit logs.')
        : workspaceId
    : empty(workspaceId!) ? fail('logAnalyticsWorkspaceId must be omitted or non-empty.') : workspaceId

@description('Azure region for the registry and its optional private endpoint.')
@minLength(1)
param location string

@description('Globally unique alphanumeric registry name; also prefixes the private endpoint.')
@minLength(5)
@maxLength(50)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('Object (principal) ID of the existing app identity that pulls images (AcrPull).')
@minLength(36)
@maxLength(36)
param pullPrincipalId string

@description('Optional object (principal) ID of the CI identity that pushes images (AcrPush).')
@minLength(36)
@maxLength(36)
param pushPrincipalId string?

@description('Registry SKU. Staging, production, private endpoints, disabled public access and IP rules require Premium.')
param sku Sku = 'Basic'

@description('Private networking; required in staging and production. Public network access is disabled unless allowPublicNetworkAccess is set.')
param privateEndpoint PrivateEndpoint?

@description('Dev or test without privateEndpoint only: keep the public endpoint. Premium denies all but allowedIpRanges; Basic and Standard stay open, Entra ID only.')
param allowPublicNetworkAccess bool = false

@description('Premium only: IPv4 addresses or CIDR ranges the registry firewall allows with allowPublicNetworkAccess.')
param allowedIpRanges string[] = []

@description('Existing Log Analytics workspace ARM ID for login and repository events; required in staging and production.')
@minLength(1)
param logAnalyticsWorkspaceId string?

var network = requirePrivateEndpoint(stage, privateEndpoint)
var checkedSku = requireSku(stage, sku, privateEndpoint != null, allowPublicNetworkAccess, !empty(allowedIpRanges))
var ipRanges = requirePublicAccess(stage, privateEndpoint != null, allowPublicNetworkAccess, allowedIpRanges)
var workspaceId = requireWorkspace(stage, logAnalyticsWorkspaceId)
var tags = { stage: stage }
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPushRoleId = '8311e382-0749-4cb8-b61a-304f252e45ec'

// The admin user and anonymous pull are disabled explicitly: Entra ID roles are the only
// registry credential. Otherwise only non-defaults are declared: zone redundancy where the
// region offers it, trusted-service bypass and AcrPull/AcrPush role mode are defaults.
// Production deletes untagged manifests after the default 7 days (Premium preview).
// Public access is disabled unless a dev or test caller opts in; Premium then denies
// all but the allow list.
resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: name
  location: location
  tags: tags
  sku: { name: checkedSku }
  properties: union(
    {
      adminUserEnabled: false
      anonymousPullEnabled: false
    },
    !allowPublicNetworkAccess
      ? { publicNetworkAccess: 'Disabled' }
      : checkedSku == 'Premium'
          ? {
              networkRuleSet: {
                defaultAction: 'Deny'
                ipRules: map(ipRanges, value => { action: 'Allow', value: value })
              }
            }
          : {},
    stage == 'prod' ? { policies: { retentionPolicy: { status: 'enabled' } } } : {}
  )
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pullPrincipalId, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource push 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (pushPrincipalId != null) {
  name: guid(registry.id, pushPrincipalId!, acrPushRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRoleId)
    principalId: pushPrincipalId!
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
          privateLinkServiceId: registry.id
          groupIds: ['registry']
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
      { name: 'registry', properties: { privateDnsZoneId: network!.privateDnsZoneId } }
    ]
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (workspaceId != null) {
  name: 'container-registry-audit'
  scope: registry
  properties: {
    workspaceId: workspaceId!
    logs: [
      { category: 'ContainerRegistryLoginEvents', enabled: true }
      { category: 'ContainerRegistryRepositoryEvents', enabled: true }
    ]
  }
}

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: registry
  properties: { level: 'CanNotDelete' }
}

output registryResourceId string = registry.id
output loginServer string = registry.properties.loginServer
