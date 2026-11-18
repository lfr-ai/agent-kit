output "search_service_id" {
  description = "Search service ARM ID; scope further role assignments here."
  value       = azapi_resource.search.id
}

output "endpoint" {
  description = "Search endpoint URL; resolves privately when private_endpoint is set. Authenticate with Entra ID, not API keys."
  value       = azapi_resource.search.output.properties.endpoint
}
