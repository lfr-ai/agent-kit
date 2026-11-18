// Managed environment inputs: availability, network topology and custom domain guards.
import { isHostName, matchesId } from './common.bicep'

// Null means absent; an empty string is a malformed ID. Check each character so embedded
// whitespace is rejected, not silently trimmed.
@export()
func requireWorkspaceId(value string?) string? =>
  value == null
    ? value
    : matchesId(value!, '/subscriptions/*/resourceGroups/*/providers/Microsoft.OperationalInsights/workspaces/*') && empty(filter(
          range(0, length(value!)),
          i => empty(trim(substring(value!, i, 1)))
        ))
        ? value
        : fail('existingLogAnalyticsWorkspaceResourceId must be omitted or a full Microsoft.OperationalInsights/workspaces ARM ID without whitespace.')

@export()
@sealed()
type Availability = {
  @minValue(0)
  @maxValue(30)
  minReplicas: int
  @minValue(1)
  @maxValue(30)
  maxReplicas: int
  zoneRedundant: bool
  deletionProtection: bool
  @description('Existing subnet ARM ID; omit or null only without zone redundancy.')
  infrastructureSubnetId: string?
}

@export()
@sealed()
type PrivateEndpoint = {
  @description('Existing subnet ARM ID in the same region; the operator owns the network.')
  subnetId: string
  @description('Existing privatelink.<location>.azurecontainerapps.io private DNS zone ARM ID, already linked to the VNets whose clients resolve the app.')
  privateDnsZoneId: string
}

@export()
@sealed()
type CustomDomain = {
  @description('Lowercase subdomain host name, such as app.example.com; apex domains are not supported.')
  hostName: string
  @description('false (default): add the host name and issue the managed certificate. true: bind the issued certificate with SNI.')
  bindCertificate: bool?
}

// The ternary compiles to if(), which ARM evaluates lazily, so short IDs never index out of range.
func isSubnetSegments(parts string[]) bool =>
  length(parts) == 11
    ? empty(parts[0]) && parts[1] == 'subscriptions' && !empty(parts[2]) && parts[3] == 'resourceGroups' && !empty(parts[4]) && parts[5] == 'providers' && parts[6] == 'Microsoft.Network' && parts[7] == 'virtualNetworks' && !empty(parts[8]) && parts[9] == 'subnets' && !empty(parts[10])
    : false

func isSubnetId(value string) bool => isSubnetSegments(split(value, '/'))

// Null-safe: an absent subnet is never a subnet ID.
func hasSubnet(value string?) bool => value == null ? false : isSubnetId(value!)

// Staging is prod-like for resilience; deletion protection stays a production-only requirement.
@export()
func requireAvailability(stage string, settings Availability) Availability =>
  contains(['dev', 'test', 'staging', 'prod'], stage) && settings.minReplicas >= 0 && settings.maxReplicas >= 1 && settings.maxReplicas <= 30 && settings.minReplicas <= settings.maxReplicas && (settings.?infrastructureSubnetId == null
      ? !settings.zoneRedundant
      : isSubnetId(settings.infrastructureSubnetId!)) && (!contains(['staging', 'prod'], stage) || (settings.zoneRedundant && settings.minReplicas >= 2)) && (stage != 'prod' || settings.deletionProtection)
    ? settings
    : fail('Invalid availability: staging and prod require zones, a subnet and minReplicas >= 2; prod also requires deletionProtection; maxReplicas must be >= minReplicas and <= 30.')

// The zone name embeds the region name, for example privatelink.westeurope.azurecontainerapps.io.
@export()
func requirePrivateEndpoint(stage string, location string, network PrivateEndpoint?) PrivateEndpoint? =>
  network == null
    ? !contains(['staging', 'prod'], stage)
        ? network
        : fail('Staging and prod require privateEndpoint (an existing subnet and privatelink.<location>.azurecontainerapps.io zone) or internalEnvironment.')
    : isSubnetId(network!.subnetId) && matchesId(
          network!.privateDnsZoneId,
          '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/privateDnsZones/privatelink.${toLower(replace(location, ' ', ''))}.azurecontainerapps.io'
        )
        ? network
        : fail('privateEndpoint needs a subnet ARM ID and the private DNS zone ARM ID of privatelink.<location>.azurecontainerapps.io for this location.')

@export()
func requireInternalEnvironment(enabled bool, subnetId string?, network PrivateEndpoint?) bool =>
  !enabled || (hasSubnet(subnetId) && network == null)
    ? enabled
    : fail('internalEnvironment requires an infrastructure subnet and cannot be combined with privateEndpoint.')

// Extra links for hub or peered VNets; the infrastructure VNet is always linked.
@export()
func requireLinkedNetworks(ids string[], internal bool, subnetId string?) string[] =>
  empty(ids) || (internal && empty(filter(
      ids,
      id => !matchesId(id, '/subscriptions/*/resourceGroups/*/providers/Microsoft.Network/virtualNetworks/*')
    )) && length(toObject(ids, id => toLower(id))) == length(ids) && !contains(
      map(ids, id => toLower(id)),
      toLower(join(take(split(subnetId ?? '', '/'), 9), '/'))
    ))
    ? ids
    : fail('linkedVirtualNetworkIds requires internalEnvironment and unique virtual network ARM IDs other than the infrastructure VNet.')

// An internal environment or a private endpoint accepts only Disabled, so Enabled is rejected offline.
// Null preserves the platform/previous setting.
@export()
func requirePublicNetworkAccess(value string?, internal bool, network PrivateEndpoint?) string? =>
  value != 'Enabled' || (!internal && network == null)
    ? value
    : fail('publicNetworkAccess Enabled cannot be combined with internalEnvironment or privateEndpoint; both require Disabled.')

// Managed certificates need a publicly reachable app, so private topologies need an operator-owned edge instead.
@export()
func requireCustomDomain(domain CustomDomain?, internal bool, network PrivateEndpoint?, publicAccess string?) CustomDomain? =>
  domain == null
    ? domain
    : isHostName(domain!.hostName) && length(split(domain!.hostName, '.')) >= 3 && !internal && network == null && publicAccess != 'Disabled'
        ? domain
        : fail('customDomain needs a lowercase subdomain host name on a public environment: no internalEnvironment, privateEndpoint or publicNetworkAccess Disabled.')
