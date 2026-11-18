output "redis_resource_id" {
  description = "Azure Managed Redis cluster ARM ID."
  value       = azapi_resource.cluster.id
}

output "host_name" {
  description = "TLS host name; resolves privately when private_endpoint is set. Authenticate with Entra ID, not keys."
  value       = azapi_resource.cluster.output.properties.hostName
}

output "port" {
  description = "TLS port of the default database."
  value       = azapi_resource.database.output.properties.port
}
