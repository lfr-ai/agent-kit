output "registry_resource_id" {
  description = "Container registry ARM ID; scope further role assignments here."
  value       = azapi_resource.registry.id
}

output "login_server" {
  description = "Registry login server for image references; resolves privately when private_endpoint is set."
  value       = azapi_resource.registry.output.properties.loginServer
}
