output "foundry_resource_id" {
  description = "Foundry (AIServices) resource ARM ID."
  value       = azapi_resource.foundry.id
}

output "project_resource_id" {
  description = "Foundry project ARM ID."
  value       = azapi_resource.project.id
}

output "openai_endpoint" {
  description = "OpenAI-compatible v1 base URL; request Entra tokens for https://ai.azure.com/.default."
  value       = "https://${var.name}.openai.azure.com/openai/v1/"
}

output "project_endpoint" {
  description = "Foundry project endpoint for the Foundry SDK."
  value       = "https://${var.name}.services.ai.azure.com/api/projects/${var.name}"
}
