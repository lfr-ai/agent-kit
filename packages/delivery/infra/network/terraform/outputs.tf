output "virtual_network_resource_id" {
  description = "Virtual network ARM ID."
  value       = azapi_resource.network.id
}

output "apps_subnet_resource_id" {
  description = "Delegated subnet ID for a Container Apps environment's infrastructure_subnet_id."
  value       = "${azapi_resource.network.id}/subnets/apps"
}

output "private_endpoint_subnet_resource_id" {
  description = "Subnet ID for a module's private_endpoint.subnet_id."
  value       = "${azapi_resource.network.id}/subnets/private-endpoints"
}

output "private_dns_zone_resource_ids" {
  description = "Created zone ARM IDs by service key, for a module's private_endpoint.private_dns_zone_id; empty by default."
  value       = { for key, zone in azapi_resource.zone : key => zone.id }
}

output "egress_mode" {
  description = "Effective apps subnet outbound path: platform, natGateway or routeTable."
  value       = local.egress_mode
}

output "nat_gateway_public_ip_resource_id" {
  description = "NAT gateway public IP ARM ID for allow-lists; null unless egress mode is natGateway."
  value       = local.nat_gateway_enabled ? azapi_resource.nat_public_ip[0].id : null
}
