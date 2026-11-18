output "account_id" {
  description = "Cosmos DB account ARM ID; scope further data-plane role assignments and alerts here."
  value       = azapi_resource.account.id
}

output "document_endpoint" {
  description = "NoSQL endpoint; resolves privately when private_endpoint is set. Authenticate with Entra ID, not an account key."
  value       = azapi_resource.account.output.properties.documentEndpoint
}

output "database_name" {
  description = "Database created by this module; null when none."
  value       = var.database == null ? null : azapi_resource.database[0].name
}

output "container_names" {
  description = "Containers created by this module."
  value       = sort(keys(azapi_resource.container))
}
