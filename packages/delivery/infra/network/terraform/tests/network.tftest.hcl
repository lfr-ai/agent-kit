# Only mocked plans: never initialize an Azure account or apply resources.
mock_provider "azapi" {}

variables {
  resource_group_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example"
  location          = "westeurope"
  name              = "sample-dev-vnet"
  stage             = "dev"
  address_prefix    = "10.20.0.0/22"
}

run "development" {
  command = plan

  # Realistic ARM IDs make subnet associations and outputs checkable in a plan.
  override_resource {
    target          = azapi_resource.apps_security_group
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/networkSecurityGroups/sample-dev-vnet-apps-nsg" }
  }
  override_resource {
    target          = azapi_resource.endpoints_security_group
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/networkSecurityGroups/sample-dev-vnet-pe-nsg" }
  }
  override_resource {
    target          = azapi_resource.network
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/virtualNetworks/sample-dev-vnet" }
  }

  assert {
    condition     = jsonencode(azapi_resource.network.body.properties.addressSpace) == jsonencode({ addressPrefixes = ["10.20.0.0/22"] })
    error_message = "The VNet owns exactly the supplied address prefix."
  }
  assert {
    condition     = jsonencode([for subnet in azapi_resource.network.body.properties.subnets : [subnet.name, subnet.properties.addressPrefix]]) == jsonencode([["apps", "10.20.0.0/23"], ["private-endpoints", "10.20.2.0/24"]])
    error_message = "Apps get the first half and private endpoints the third quarter; the last quarter stays free."
  }
  assert {
    condition     = jsonencode(azapi_resource.network.body.properties.subnets[0].properties) == jsonencode({ addressPrefix = "10.20.0.0/23", networkSecurityGroup = { id = azapi_resource.apps_security_group.id }, delegations = [{ name = "Microsoft.App.environments", properties = { serviceName = "Microsoft.App/environments" } }], defaultOutboundAccess = false })
    error_message = "The apps subnet is delegated to Container Apps environments, has its NSG and no default outbound access."
  }
  assert {
    condition     = jsonencode(azapi_resource.network.body.properties.subnets[1].properties) == jsonencode({ addressPrefix = "10.20.2.0/24", networkSecurityGroup = { id = azapi_resource.endpoints_security_group.id }, privateEndpointNetworkPolicies = "Enabled", defaultOutboundAccess = false })
    error_message = "The private endpoint subnet has its NSG, enforced endpoint network policies and no default outbound access."
  }
  assert {
    condition     = azapi_resource.apps_security_group.name == "sample-dev-vnet-apps-nsg" && azapi_resource.endpoints_security_group.name == "sample-dev-vnet-pe-nsg" && azapi_resource.apps_security_group.body == null && azapi_resource.endpoints_security_group.body == null
    error_message = "Each subnet gets its own NSG with no custom rules."
  }
  assert {
    condition     = length(azapi_resource.zone) == 0 && length(azapi_resource.zone_link) == 0 && length(azapi_resource.protection) == 0 && length(azapi_resource.zone_protection) == 0
    error_message = "Development creates no private DNS zones or locks unless requested."
  }
  assert {
    condition     = output.egress_mode == "platform" && length(azapi_resource.nat_public_ip) == 0 && length(azapi_resource.nat_gateway) == 0 && output.nat_gateway_public_ip_resource_id == null
    error_message = "Development keeps the platform outbound path and creates no NAT gateway by default."
  }
  assert {
    condition     = output.virtual_network_resource_id == azapi_resource.network.id && output.apps_subnet_resource_id == "${azapi_resource.network.id}/subnets/apps" && output.private_endpoint_subnet_resource_id == "${azapi_resource.network.id}/subnets/private-endpoints" && jsonencode(output.private_dns_zone_resource_ids) == jsonencode({})
    error_message = "Outputs are the VNet, subnet and (empty) zone IDs."
  }
}

run "largest_prefix" {
  command = plan
  variables {
    address_prefix = "10.20.0.0/16"
  }
  assert {
    condition     = jsonencode([for subnet in azapi_resource.network.body.properties.subnets : subnet.properties.addressPrefix]) == jsonencode(["10.20.0.0/17", "10.20.128.0/18"])
    error_message = "A /16 splits into a /17 for apps and a /18 for private endpoints."
  }
}

run "smallest_prefix" {
  command = plan
  variables {
    address_prefix = "10.20.0.0/24"
  }
  assert {
    condition     = jsonencode([for subnet in azapi_resource.network.body.properties.subnets : subnet.properties.addressPrefix]) == jsonencode(["10.20.0.0/25", "10.20.0.128/26"])
    error_message = "A /24 still leaves Container Apps a /25, above its /27 minimum."
  }
}

run "production" {
  command = plan
  variables {
    name              = "sample-prod-vnet"
    stage             = "prod"
    private_dns_zones = ["keyVault", "redis", "postgresql", "blob", "queue", "table", "file", "dfs", "containerRegistry", "search", "cognitiveServices", "openai", "aiServices", "cosmosDb", "containerApps", "monitor", "oms", "ods", "agentsvc"]
  }
  override_resource {
    target          = azapi_resource.network
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/virtualNetworks/sample-prod-vnet" }
  }
  override_resource {
    target          = azapi_resource.zone["keyVault"]
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net" }
  }
  override_resource {
    target          = azapi_resource.zone["containerApps"]
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/privateDnsZones/privatelink.westeurope.azurecontainerapps.io" }
  }
  override_resource {
    target          = azapi_resource.nat_public_ip[0]
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/publicIPAddresses/sample-prod-vnet-nat-pip" }
  }
  override_resource {
    target          = azapi_resource.nat_gateway[0]
    override_during = plan
    values          = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.Network/natGateways/sample-prod-vnet-nat" }
  }
  assert {
    condition     = jsonencode(sort([for zone in azapi_resource.zone : zone.name])) == jsonencode(sort(["privatelink.vaultcore.azure.net", "privatelink.redis.azure.net", "privatelink.postgres.database.azure.com", "privatelink.blob.core.windows.net", "privatelink.queue.core.windows.net", "privatelink.table.core.windows.net", "privatelink.file.core.windows.net", "privatelink.dfs.core.windows.net", "privatelink.azurecr.io", "privatelink.search.windows.net", "privatelink.cognitiveservices.azure.com", "privatelink.openai.azure.com", "privatelink.services.ai.azure.com", "privatelink.documents.azure.com", "privatelink.westeurope.azurecontainerapps.io", "privatelink.monitor.azure.com", "privatelink.oms.opinsights.azure.com", "privatelink.ods.opinsights.azure.com", "privatelink.agentsvc.azure-automation.net"]))
    error_message = "Each requested key creates its documented privatelink zone; Container Apps uses the region name."
  }
  assert {
    condition     = alltrue([for zone in azapi_resource.zone : zone.location == "global" && zone.parent_id == var.resource_group_id])
    error_message = "Private DNS zones are global resources in the supplied group."
  }
  assert {
    condition     = jsonencode(sort(keys(azapi_resource.zone_link))) == jsonencode(sort(var.private_dns_zones)) && alltrue([for link in azapi_resource.zone_link : link.name == "sample-prod-vnet" && link.location == "global" && jsonencode(link.body.properties) == jsonencode({ virtualNetwork = { id = azapi_resource.network.id }, registrationEnabled = false })])
    error_message = "Each zone is linked to this VNet without auto-registration."
  }
  assert {
    condition     = azapi_resource.zone_link["keyVault"].parent_id == azapi_resource.zone["keyVault"].id && azapi_resource.zone_link["containerApps"].parent_id == azapi_resource.zone["containerApps"].id
    error_message = "Each link belongs to its own zone."
  }
  assert {
    condition     = length(azapi_resource.protection) == 1 && azapi_resource.protection[0].parent_id == azapi_resource.network.id && azapi_resource.protection[0].body.properties.level == "CanNotDelete"
    error_message = "Production must create its VNet-scoped deletion lock."
  }
  assert {
    condition     = jsonencode(sort(keys(azapi_resource.zone_protection))) == jsonencode(sort(var.private_dns_zones)) && alltrue([for lock in azapi_resource.zone_protection : lock.name == "deletion-protection" && lock.body.properties.level == "CanNotDelete"])
    error_message = "Production locks each created zone."
  }
  assert {
    condition     = azapi_resource.zone_protection["keyVault"].parent_id == azapi_resource.zone["keyVault"].id && azapi_resource.zone_protection["containerApps"].parent_id == azapi_resource.zone["containerApps"].id
    error_message = "Each zone lock is scoped to its own zone."
  }
  assert {
    condition     = jsonencode(sort(keys(output.private_dns_zone_resource_ids))) == jsonencode(sort(var.private_dns_zones)) && output.private_dns_zone_resource_ids["keyVault"] == azapi_resource.zone["keyVault"].id
    error_message = "The zone output maps each service key to its zone ID."
  }
  assert {
    condition     = output.egress_mode == "natGateway" && azapi_resource.nat_public_ip[0].name == "sample-prod-vnet-nat-pip" && jsonencode(azapi_resource.nat_public_ip[0].body) == jsonencode({ sku = { name = "Standard", tier = "Regional" }, properties = { publicIPAddressVersion = "IPv4", publicIPAllocationMethod = "Static" } })
    error_message = "Production defaults to a NAT gateway with one static Standard IPv4 address."
  }
  assert {
    condition     = azapi_resource.nat_gateway[0].name == "sample-prod-vnet-nat" && jsonencode(azapi_resource.nat_gateway[0].body) == jsonencode({ sku = { name = "Standard" }, properties = { publicIpAddresses = [{ id = azapi_resource.nat_public_ip[0].id }] } })
    error_message = "The NAT gateway uses the created public IP."
  }
  assert {
    condition     = azapi_resource.network.body.properties.subnets[0].properties.natGateway.id == azapi_resource.nat_gateway[0].id && !contains(keys(azapi_resource.network.body.properties.subnets[0].properties), "routeTable") && !contains(keys(azapi_resource.network.body.properties.subnets[1].properties), "natGateway")
    error_message = "Only the apps subnet is associated with the NAT gateway."
  }
  assert {
    condition     = azapi_resource.nat_protection[0].parent_id == azapi_resource.nat_gateway[0].id && azapi_resource.nat_ip_protection[0].parent_id == azapi_resource.nat_public_ip[0].id && azapi_resource.nat_protection[0].body.properties.level == "CanNotDelete" && output.nat_gateway_public_ip_resource_id == azapi_resource.nat_public_ip[0].id
    error_message = "Production locks the NAT gateway and its public IP, and outputs the IP ID."
  }
}

run "route_table_egress" {
  command = plan
  variables {
    stage  = "staging"
    egress = { mode = "routeTable", route_table_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/hub/providers/Microsoft.Network/routeTables/to-firewall" }
  }
  assert {
    condition     = output.egress_mode == "routeTable" && azapi_resource.network.body.properties.subnets[0].properties.routeTable.id == var.egress.route_table_id && !contains(keys(azapi_resource.network.body.properties.subnets[0].properties), "natGateway") && length(azapi_resource.nat_gateway) == 0 && length(azapi_resource.nat_public_ip) == 0
    error_message = "A supplied route table replaces the staging NAT default on the apps subnet."
  }
}

run "explicit_platform_production" {
  command = plan
  variables {
    stage  = "prod"
    egress = { mode = "platform" }
  }
  assert {
    condition     = output.egress_mode == "platform" && length(azapi_resource.nat_gateway) == 0 && length(azapi_resource.nat_protection) == 0 && length(azapi_resource.nat_ip_protection) == 0 && !contains(keys(azapi_resource.network.body.properties.subnets[0].properties), "natGateway")
    error_message = "An explicit platform egress opts production out of the NAT gateway cost."
  }
}

run "zones_outside_production" {
  command = plan
  variables {
    location          = "West Europe"
    stage             = "test"
    private_dns_zones = ["containerApps"]
  }
  assert {
    condition     = length(azapi_resource.zone) == 1 && azapi_resource.zone["containerApps"].name == "privatelink.westeurope.azurecontainerapps.io" && length(azapi_resource.zone_link) == 1
    error_message = "Zones and links are available outside production; the Container Apps zone uses the normalized region name."
  }
  assert {
    condition     = length(azapi_resource.protection) == 0 && length(azapi_resource.zone_protection) == 0
    error_message = "Optional zones do not turn test into production."
  }
}

run "reject_large_prefix" {
  command = plan
  variables {
    address_prefix = "10.0.0.0/15"
  }
  expect_failures = [var.address_prefix]
}

run "reject_small_prefix" {
  command = plan
  variables {
    address_prefix = "10.20.0.0/25"
  }
  expect_failures = [var.address_prefix]
}

run "reject_host_address" {
  command = plan
  variables {
    address_prefix = "10.20.0.5/22"
  }
  expect_failures = [var.address_prefix]
}

run "reject_ipv6_prefix" {
  command = plan
  variables {
    address_prefix = "fd00::/16"
  }
  expect_failures = [var.address_prefix]
}

run "reject_unknown_zone" {
  command = plan
  variables {
    private_dns_zones = ["sql"]
  }
  expect_failures = [var.private_dns_zones]
}

run "reject_duplicate_zone" {
  command = plan
  variables {
    private_dns_zones = ["keyVault", "keyVault"]
  }
  expect_failures = [var.private_dns_zones]
}

run "reject_route_table_without_id" {
  command = plan
  variables {
    egress = { mode = "routeTable" }
  }
  expect_failures = [var.egress]
}