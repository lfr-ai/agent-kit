output "vault_resource_id" {
  description = "Key Vault ARM ID; scope further role assignments here."
  value       = azapi_resource.vault.id
}

output "vault_uri" {
  description = "Vault URI for SDK clients; resolves privately when private_endpoint is set. Authenticate with Entra ID."
  value       = azapi_resource.vault.output.properties.vaultUri
}
