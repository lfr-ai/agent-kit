locals {
  tags = { stage = var.stage }
  # cidrsubnet() takes the added bits; Bicep cidrSubnet() takes the resulting prefix length.
  apps_prefix              = cidrsubnet(var.address_prefix, 1, 0)
  private_endpoints_prefix = cidrsubnet(var.address_prefix, 2, 2)
  zones                    = { for key in var.private_dns_zones : key => local.zone_names[key] }
  egress_mode              = var.egress == null ? (contains(["staging", "prod"], var.stage) ? "natGateway" : "platform") : var.egress.mode
  nat_gateway_enabled      = local.egress_mode == "natGateway"
  # Keyed by the subnet property each mode sets; platform sets neither.
  apps_egress = {
    for property, id in {
      natGateway = one(azapi_resource.nat_gateway[*].id)
      routeTable = try(var.egress.route_table_id, null)
    } : property => { id = id } if property == local.egress_mode
  }
}

# One static IPv4 address; a Standard NAT gateway is zonal or no-zone, not zone-redundant.
resource "azapi_resource" "nat_public_ip" {
  count     = local.nat_gateway_enabled ? 1 : 0
  type      = "Microsoft.Network/publicIPAddresses@2025-01-01"
  name      = "${var.name}-nat-pip"
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    sku = { name = "Standard", tier = "Regional" }
    properties = {
      publicIPAddressVersion   = "IPv4"
      publicIPAllocationMethod = "Static"
    }
  }
  response_export_values = []
}

resource "azapi_resource" "nat_gateway" {
  count     = local.nat_gateway_enabled ? 1 : 0
  type      = "Microsoft.Network/natGateways@2025-01-01"
  name      = "${var.name}-nat"
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    sku        = { name = "Standard" }
    properties = { publicIpAddresses = [{ id = azapi_resource.nat_public_ip[0].id }] }
  }
  response_export_values = []
}

# No custom rules: the default rules deny inbound Internet traffic.
resource "azapi_resource" "apps_security_group" {
  type                   = "Microsoft.Network/networkSecurityGroups@2025-01-01"
  name                   = "${var.name}-apps-nsg"
  parent_id              = var.resource_group_id
  location               = var.location
  tags                   = local.tags
  response_export_values = []
}

resource "azapi_resource" "endpoints_security_group" {
  type                   = "Microsoft.Network/networkSecurityGroups@2025-01-01"
  name                   = "${var.name}-pe-nsg"
  parent_id              = var.resource_group_id
  location               = var.location
  tags                   = local.tags
  response_export_values = []
}

# Subnets stay inline so a VNet update never removes them. API versions up to
# 2026-03-31 default to defaultOutboundAccess true, and private endpoint policies to off.
resource "azapi_resource" "network" {
  type      = "Microsoft.Network/virtualNetworks@2025-01-01"
  name      = var.name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = local.tags
  body = {
    properties = {
      addressSpace = { addressPrefixes = [var.address_prefix] }
      subnets = [
        {
          name = "apps"
          properties = merge({
            addressPrefix        = local.apps_prefix
            networkSecurityGroup = { id = azapi_resource.apps_security_group.id }
            delegations = [{
              name       = "Microsoft.App.environments"
              properties = { serviceName = "Microsoft.App/environments" }
            }]
            defaultOutboundAccess = false
          }, local.apps_egress)
        },
        {
          name = "private-endpoints"
          properties = {
            addressPrefix                  = local.private_endpoints_prefix
            networkSecurityGroup           = { id = azapi_resource.endpoints_security_group.id }
            privateEndpointNetworkPolicies = "Enabled"
            defaultOutboundAccess          = false
          }
        },
      ]
    }
  }
  response_export_values = []
}

resource "azapi_resource" "zone" {
  for_each               = local.zones
  type                   = "Microsoft.Network/privateDnsZones@2024-06-01"
  name                   = each.value
  parent_id              = var.resource_group_id
  location               = "global"
  tags                   = local.tags
  response_export_values = []
}

# registrationEnabled has no documented API default, so it is explicit.
resource "azapi_resource" "zone_link" {
  for_each  = azapi_resource.zone
  type      = "Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01"
  name      = var.name
  parent_id = each.value.id
  location  = "global"
  tags      = local.tags
  body = {
    properties = {
      virtualNetwork      = { id = azapi_resource.network.id }
      registrationEnabled = false
    }
  }
  response_export_values = []
}

# Resource-scoped: never protects unrelated resources in the caller's group.
resource "azapi_resource" "protection" {
  count                  = var.stage == "prod" ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.network.id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []
}

resource "azapi_resource" "zone_protection" {
  for_each               = { for key, zone in azapi_resource.zone : key => zone.id if var.stage == "prod" }
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = each.value
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []

  # Create the inherited lock last; reverse destroy must unlock before the links.
  depends_on = [azapi_resource.zone_link]
}

resource "azapi_resource" "nat_protection" {
  count                  = var.stage == "prod" && local.nat_gateway_enabled ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.nat_gateway[0].id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []

  # Reverse destroy unlocks before the subnet association is removed.
  depends_on = [azapi_resource.network]
}

resource "azapi_resource" "nat_ip_protection" {
  count                  = var.stage == "prod" && local.nat_gateway_enabled ? 1 : 0
  type                   = "Microsoft.Authorization/locks@2020-05-01"
  name                   = "deletion-protection"
  parent_id              = azapi_resource.nat_public_ip[0].id
  body                   = { properties = { level = "CanNotDelete" } }
  response_export_values = []

  depends_on = [azapi_resource.nat_gateway]
}
