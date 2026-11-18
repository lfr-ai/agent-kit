@description('Internal ACA default domain; not the Private Link zone.')
param domain string
param address string
param networkId string
@description('Extra VNets, such as a hub or peered VNets, whose clients resolve the environment.')
param linkedNetworkIds string[]
param name string
param tags { *: string }
param deletionProtection bool

// Five-minute TTL for the wildcard and apex A records of the environment static IP.
var dnsTtlSeconds = 300

resource zone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: domain
  location: 'global'
  tags: tags
}

resource link 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zone
  name: name
  location: 'global'
  properties: {
    virtualNetwork: { id: networkId }
    registrationEnabled: false
  }
}

resource extraLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for id in linkedNetworkIds: {
    parent: zone
    // Deterministic per VNet and case-insensitive, so reordering the list never renames a link.
    name: '${name}-${guid(toLower(id))}'
    location: 'global'
    properties: {
      virtualNetwork: { id: id }
      registrationEnabled: false
    }
  }
]

resource records 'Microsoft.Network/privateDnsZones/A@2024-06-01' = [
  for record in ['*', '@']: {
    parent: zone
    name: record
    properties: {
      ttl: dnsTtlSeconds
      aRecords: [{ ipv4Address: address }]
    }
  }
]

resource protection 'Microsoft.Authorization/locks@2020-05-01' = if (deletionProtection) {
  name: 'foundation-protection'
  scope: zone
  properties: { level: 'CanNotDelete' }
}
