output "document_intelligence_resource_id" {
  description = "Document Intelligence resource ARM ID."
  value       = azapi_resource.account.id
}

output "endpoint" {
  description = "Custom-subdomain endpoint; request Entra tokens for https://cognitiveservices.azure.com/.default."
  value       = azapi_resource.account.output.properties.endpoint
}
