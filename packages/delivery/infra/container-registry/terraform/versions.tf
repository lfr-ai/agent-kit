terraform {
  required_version = ">= 1.11.3, < 2.0.0"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "= 2.13.0"
    }
  }
}

# The consumer owns provider authentication, subscription and backend.
# No provider block: this directory is also a reusable child module.
