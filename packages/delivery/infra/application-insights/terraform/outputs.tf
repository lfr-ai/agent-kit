output "application_insights_resource_id" {
  description = "Application Insights ARM ID."
  value       = azapi_resource.component.id
}

output "connection_string" {
  description = "An identifier, not a credential: test and prod ingestion still needs an Entra ID token."
  value       = azapi_resource.component.output.properties.ConnectionString
}
