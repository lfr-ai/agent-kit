output "api_management_resource_id" {
  description = "API Management instance ARM ID for caller-owned integrations."
  value       = azapi_resource.service.id
}

output "gateway_url" {
  description = "Gateway base URL; the API is served at its root."
  value       = azapi_resource.service.output.properties.gatewayUrl
}

output "principal_id" {
  description = "Grant this identity access to the backend when it needs authentication-managed-identity."
  value       = azapi_resource.service.identity[0].principal_id
}
