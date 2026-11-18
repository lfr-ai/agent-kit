output "activity_log_setting_id" {
  description = "ARM ID of the subscription Activity Log diagnostic setting."
  value       = azapi_resource.activity_log.id
}
