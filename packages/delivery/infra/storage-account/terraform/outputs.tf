output "storage_account_id" {
  description = "Storage account ARM ID. The runtime identity already has Storage Blob Data Contributor on each managed container (or this account when none is managed); grant read-only consumers Storage Blob Data Reader through their owner."
  value       = azapi_resource.account.id
}

output "blob_endpoint" {
  description = "Blob service endpoint; resolves privately when private_endpoint is set. Authenticate with Entra ID, not an account key."
  value       = azapi_resource.account.output.properties.primaryEndpoints.blob
}

output "container_names" {
  description = "Blob containers created by this module."
  value       = sort([for container in azapi_resource.container : container.name])
}
