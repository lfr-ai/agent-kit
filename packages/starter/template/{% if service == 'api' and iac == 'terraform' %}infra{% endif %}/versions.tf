terraform {
  required_version = "= 1.16.7"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "= 2.13.0"
    }
  }

  backend "azurerm" {}
}
