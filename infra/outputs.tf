output "vm_public_ip" {
  description = "Adresse IP publique de la VM de production."
  value       = azurerm_public_ip.main.ip_address
}

output "ssh_command" {
  description = "Commande pour se connecter à la VM."
  value       = "ssh ${var.admin_username}@${azurerm_public_ip.main.ip_address}"
}

output "storage_account_name" {
  description = "Nom du compte de stockage Azure créé."
  value       = azurerm_storage_account.main.name
}

output "blob_container" {
  description = "Conteneur Blob prévu pour les fichiers de transactions."
  value       = azurerm_storage_container.transactions.name
}
