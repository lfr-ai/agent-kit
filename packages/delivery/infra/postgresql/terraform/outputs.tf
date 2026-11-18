output "server_id" {
  description = "PostgreSQL flexible server ARM ID; scope further role assignments and alerts here."
  value       = azapi_resource.server.id
}

output "fqdn" {
  description = "Server host name; resolves privately when private_endpoint is set. Authenticate with an Entra token, not a password."
  value       = azapi_resource.server.output.properties.fullyQualifiedDomainName
}

output "database_name" {
  description = "Application database name."
  value       = azapi_resource.database.name
}
