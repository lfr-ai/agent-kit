terraform {
  required_version = ">= 1.9"
}

output "label" {
  description = "Value echoed by the fixture root module."
  value       = "fixture"
}
