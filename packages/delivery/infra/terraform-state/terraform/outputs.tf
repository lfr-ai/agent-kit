output "storage_account_resource_id" {
  description = "State storage account ARM ID."
  value       = azapi_resource.account.id
}

output "storage_account_name" {
  description = "Value for the azurerm backend storage_account_name."
  value       = azapi_resource.account.name
}

output "container_name" {
  description = "Value for the azurerm backend container_name."
  value       = azapi_resource.container.name
}
