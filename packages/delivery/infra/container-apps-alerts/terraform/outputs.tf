output "action_group_id" {
  description = "Action group ARM ID (created or caller-owned); null when unmonitored. Reuse it for further alert rules on the same app."
  value       = local.action_group_id
}
