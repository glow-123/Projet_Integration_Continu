terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# L'authentification vient de la session `az login` (ou du Cloud Shell Azure).
# L'identifiant de souscription est lu dans la variable d'environnement ARM_SUBSCRIPTION_ID.
provider "azurerm" {
  features {}
}
