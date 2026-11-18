@description('Service whose privatelink DNS zone this composition creates and links to the VNet.')
type PrivateDnsZone =
  | 'keyVault'
  | 'redis'
  | 'postgresql'
  | 'blob'
  | 'queue'
  | 'table'
  | 'file'
  | 'dfs'
  | 'containerRegistry'
  | 'search'
  | 'cognitiveServices'
  | 'openai'
  | 'aiServices'
  | 'cosmosDb'
  | 'containerApps'
  | 'monitor'
  | 'oms'
  | 'ods'
  | 'agentsvc'

@description('Outbound path for the apps subnet, which has no default outbound access.')
type Egress = {
  @description('platform: no NAT gateway or route table; natGateway: a NAT gateway with one static public IP; routeTable: an existing route table, for example to a hub firewall.')
  mode: 'platform' | 'natGateway' | 'routeTable'

  @description('Existing route table ARM ID; required for routeTable, otherwise omitted.')
  routeTableId: string?
}

func isNumber(text string, low int, high int) bool =>
  length(text) >= 1 && length(text) <= 3 && empty(reduce(
    ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'],
    text,
    (rest, digit) => replace(rest, digit, '')
  )) && string(int(text)) == text && int(text) >= low && int(text) <= high

// VNet prefix-length bounds. A /16 is the largest network this layout splits; a /24
// still leaves Container Apps a /25, above its /27 minimum. Functions, not variables,
// because user-defined functions cannot read template variables.
func minPrefixLength() int => 16

func maxPrefixLength() int => 24

func address(prefix string) string => first(split(prefix, '/'))

func octets(prefix string) string[] => split(address(prefix), '.')

// Syntax is checked first: parseCidr() reads leading zeros as octal and accepts IPv6.
// A host address such as 10.20.0.5/22 fails the network comparison.
func isAddressPrefix(prefix string) bool =>
  length(split(prefix, '/')) == 2 && isNumber(last(split(prefix, '/')), minPrefixLength(), maxPrefixLength()) && length(octets(prefix)) == 4 && empty(filter(
    octets(prefix),
    octet => !isNumber(octet, 0, 255)
  )) && parseCidr(prefix).network == address(prefix)

// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireAddressPrefix(prefix string) string =>
  isAddressPrefix(prefix)
    ? prefix
    : fail('addressPrefix must be one IPv4 network address in CIDR notation from /16 to /24, for example 10.20.0.0/22.')

@export()
func requirePrivateDnsZones(zones PrivateDnsZone[]) PrivateDnsZone[] => length(union(zones, [])) == length(zones) ? zones : fail('privateDnsZones must not repeat a service key.')

func isRouteTablePath(parts string[]) bool =>
  length(parts) == 9 && toLower('${parts[0]}/${parts[1]}/${parts[3]}/${parts[5]}/${parts[6]}/${parts[7]}') == '/subscriptions/resourcegroups/providers/microsoft.network/routetables' && !empty(parts[2]) && !empty(parts[4]) && !empty(parts[8])

func isRouteTableId(id string) bool => isRouteTablePath(split(id, '/'))

@export()
func requireEgress(egress Egress) Egress =>
  (egress.mode == 'routeTable' ? isRouteTableId(egress.?routeTableId ?? '') : egress.?routeTableId == null)
    ? egress
    : fail('egress.routeTableId must be a route table ARM ID when mode is routeTable, and omitted otherwise.')

@description('Azure region name, for example westeurope; also names the Container Apps private DNS zone.')
@minLength(1)
param location string

@description('Virtual network name: 2-64 letters, digits, underscores, periods or hyphens; also prefixes its NSGs and names the DNS zone links.')
@minLength(2)
@maxLength(64)
param name string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('One IPv4 network CIDR from /16 to /24. Apps get the first half, private endpoints the third quarter; the last quarter stays free.')
param addressPrefix string

@description('Private DNS zones to create and link to this VNet. Default none: a platform-owned hub usually owns them.')
param privateDnsZones PrivateDnsZone[] = []

@description('Apps subnet outbound path. Default: natGateway for staging and prod, platform for dev and test. Set it explicitly to override the cost decision.')
param egress Egress?

var prefix = requireAddressPrefix(addressPrefix)
var zoneKeys = requirePrivateDnsZones(privateDnsZones)
var egressSettings = requireEgress(egress ?? { mode: contains(['staging', 'prod'], stage) ? 'natGateway' : 'platform' })
var natGatewayEnabled = egressSettings.mode == 'natGateway'
var appsEgress = egressSettings.mode == 'natGateway'
  ? { natGateway: { id: natGateway.id } }
  : egressSettings.mode == 'routeTable' ? { routeTable: { id: egressSettings.routeTableId! } } : {}
var tags = { stage: stage }
// cidrSubnet() takes the resulting prefix length; Terraform cidrsubnet() takes the added bits.
var prefixLength = parseCidr(prefix).cidr
var appsSubnetName = 'apps'
var endpointsSubnetName = 'private-endpoints'
// Azure public-cloud zone names from the Private Link DNS reference.
var zoneNames = {
  keyVault: 'privatelink.vaultcore.azure.net'
  redis: 'privatelink.redis.azure.net'
  postgresql: 'privatelink.postgres.database.azure.com'
  #disable-next-line no-hardcoded-env-urls
  blob: 'privatelink.blob.core.windows.net'
  #disable-next-line no-hardcoded-env-urls
  queue: 'privatelink.queue.core.windows.net'
  #disable-next-line no-hardcoded-env-urls
  table: 'privatelink.table.core.windows.net'
  #disable-next-line no-hardcoded-env-urls
  file: 'privatelink.file.core.windows.net'
  #disable-next-line no-hardcoded-env-urls
  dfs: 'privatelink.dfs.core.windows.net'
  containerRegistry: 'privatelink.azurecr.io'
  search: 'privatelink.search.windows.net'
  cognitiveServices: 'privatelink.cognitiveservices.azure.com'
  openai: 'privatelink.openai.azure.com'
  aiServices: 'privatelink.services.ai.azure.com'
  cosmosDb: 'privatelink.documents.azure.com'
  // Same normalization as the container-apps guard: West Europe -> westeurope.
  containerApps: 'privatelink.${toLower(replace(location, ' ', ''))}.azurecontainerapps.io'
  // Azure Monitor Private Link Scope; it also needs the blob zone.
  monitor: 'privatelink.monitor.azure.com'
  oms: 'privatelink.oms.opinsights.azure.com'
  ods: 'privatelink.ods.opinsights.azure.com'
  agentsvc: 'privatelink.agentsvc.azure-automation.net'
}

// One static IPv4 address; a Standard NAT gateway is zonal or no-zone, not zone-redundant.
resource natPublicIp 'Microsoft.Network/publicIPAddresses@2025-01-01' = if (natGatewayEnabled) {
  name: '${name}-nat-pip'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Regional' }
  properties: {
    publicIPAddressVersion: 'IPv4'
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2025-01-01' = if (natGatewayEnabled) {
  name: '${name}-nat'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    publicIpAddresses: [{ id: natPublicIp.id }]
  }
}

// No custom rules: the default rules deny inbound Internet traffic.
resource appsSecurityGroup 'Microsoft.Network/networkSecurityGroups@2025-01-01' = {
  name: '${name}-apps-nsg'
  location: location
  tags: tags
}

resource endpointsSecurityGroup 'Microsoft.Network/networkSecurityGroups@2025-01-01' = {
  name: '${name}-pe-nsg'
  location: location
  tags: tags
}

// Subnets stay inline so a VNet redeployment never removes them. API versions up to
// 2026-03-31 default to defaultOutboundAccess true, and private endpoint policies to off.
resource network 'Microsoft.Network/virtualNetworks@2025-01-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [prefix] }
    subnets: [
      {
        name: appsSubnetName
        properties: union(
          {
            addressPrefix: cidrSubnet(prefix, prefixLength + 1, 0)
            networkSecurityGroup: { id: appsSecurityGroup.id }
            delegations: [
              {
                name: 'Microsoft.App.environments'
                properties: { serviceName: 'Microsoft.App/environments' }
              }
            ]
            defaultOutboundAccess: false
          },
          appsEgress
        )
      }
      {
        name: endpointsSubnetName
        properties: {
          addressPrefix: cidrSubnet(prefix, prefixLength + 2, 2)
          networkSecurityGroup: { id: endpointsSecurityGroup.id }
          privateEndpointNetworkPolicies: 'Enabled'
          defaultOutboundAccess: false
        }
      }
    ]
  }
}

resource zones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for key in zoneKeys: {
    name: zoneNames[key]
    location: 'global'
    tags: tags
  }
]

// registrationEnabled has no documented API default, so it is explicit.
resource zoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (key, index) in zoneKeys: {
    parent: zones[index]
    name: name
    location: 'global'
    tags: tags
    properties: {
      virtualNetwork: { id: network.id }
      registrationEnabled: false
    }
  }
]

// Resource-scoped: never protects unrelated resources in the caller's group.
resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod') {
  name: 'deletion-protection'
  scope: network
  properties: { level: 'CanNotDelete' }
}

resource zoneProtection 'Microsoft.Authorization/locks@2020-05-01' = [
  for (key, index) in zoneKeys: if (stage == 'prod') {
    name: 'deletion-protection'
    scope: zones[index]
    properties: { level: 'CanNotDelete' }
  }
]

resource natProtection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod' && natGatewayEnabled) {
  name: 'deletion-protection'
  scope: natGateway
  properties: { level: 'CanNotDelete' }
}

resource natIpProtection 'Microsoft.Authorization/locks@2020-05-01' = if (stage == 'prod' && natGatewayEnabled) {
  name: 'deletion-protection'
  scope: natPublicIp
  properties: { level: 'CanNotDelete' }
}

output virtualNetworkResourceId string = network.id
output appsSubnetResourceId string = '${network.id}/subnets/${appsSubnetName}'
output privateEndpointSubnetResourceId string = '${network.id}/subnets/${endpointsSubnetName}'
output privateDnsZoneResourceIds { *: string } = toObject(
  zoneKeys,
  key => key,
  key => resourceId('Microsoft.Network/privateDnsZones', zoneNames[key])
)
output egressMode string = egressSettings.mode
output natGatewayPublicIpResourceId string? = natGatewayEnabled ? natPublicIp.id : null
