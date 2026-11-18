output "app_resource_id" {
  description = "Container App ARM ID."
  value       = azapi_resource.app.id
}

output "environment_resource_id" {
  description = "Managed environment ARM ID."
  value       = azapi_resource.environment.id
}

output "workspace_resource_id" {
  description = "Log Analytics ARM ID, not a workspace shared key."
  value       = local.workspace_id
}

output "managed_identity_resource_id" {
  description = "Runtime and optional secret/image access identity."
  value       = local.identity_id
}

output "url" {
  description = "HTTPS endpoint; with private_endpoint it resolves privately and accepts no public traffic. Authentication is application/operator-owned."
  value       = "https://${azapi_resource.app.output.properties.configuration.ingress.fqdn}"
}

output "environment_default_domain" {
  description = "<unique>.<location>.azurecontainerapps.io; its first label is the private DNS record name."
  value       = azapi_resource.environment.output.properties.defaultDomain
}

output "private_endpoint_resource_id" {
  description = "Private endpoint ARM ID, or null without private_endpoint."
  value       = var.private_endpoint == null ? null : azapi_resource.endpoint[0].id
}

output "auth_callback_url" {
  description = "Redirect URI to register on the Entra app; null unless authentication.sign_in is true."
  value       = !local.auth_sign_in ? null : "https://${coalesce(local.auth_host, local.domain_host, azapi_resource.app.output.properties.configuration.ingress.fqdn)}/.auth/login/aad/callback"
}

output "custom_domain_cname_target" {
  description = "CNAME target for custom_domain.host_name: the app FQDN."
  value       = azapi_resource.app.output.properties.configuration.ingress.fqdn
}

output "custom_domain_txt_record_name" {
  description = "TXT record name for domain verification, asuid.<host_name>; null without custom_domain."
  value       = local.domain_host == null ? null : "asuid.${local.domain_host}"
}

output "custom_domain_verification_id" {
  description = "TXT record value for domain verification, or null until the platform reports it; not a secret."
  value       = try(azapi_resource.environment.output.properties.customDomainConfiguration.customDomainVerificationId, null)
}
