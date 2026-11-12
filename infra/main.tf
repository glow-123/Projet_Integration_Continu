# ---------------------------------------------------------------------------
# Infrastructure de PRODUCTION de la pipeline data, décrite en code.
#
#   Groupe de ressources
#     ├─ Réseau virtuel + sous-réseau + pare-feu (NSG : SSH uniquement)
#     ├─ IP publique + carte réseau
#     ├─ Machine virtuelle Ubuntu  -> au démarrage : installe Docker, clone le dépôt
#     │                               et lance docker-compose.prod.yml
#     │                               (PostgreSQL + S3 RustFS + pipeline)
#     └─ Compte de stockage Azure + conteneur Blob (archive des fichiers CSV)
# ---------------------------------------------------------------------------

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.prefix}"
  location = var.location
  tags     = var.tags
}

# --- Réseau -----------------------------------------------------------------

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.prefix}"
  address_space       = ["10.10.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
}

resource "azurerm_subnet" "main" {
  name                 = "snet-${var.prefix}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.1.0/24"]
}

# Pare-feu : on n'ouvre que le SSH. PostgreSQL et S3 ne sont PAS exposés
# (docker-compose.prod.yml ne publie aucun port).
resource "azurerm_network_security_group" "main" {
  name                = "nsg-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags

  security_rule {
    name                       = "allow-ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.ssh_allowed_cidr
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "main" {
  subnet_id                 = azurerm_subnet.main.id
  network_security_group_id = azurerm_network_security_group.main.id
}

resource "azurerm_public_ip" "main" {
  name                = "pip-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

resource "azurerm_network_interface" "main" {
  name                = "nic-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.main.id
  }
}

# --- Machine virtuelle ------------------------------------------------------

resource "azurerm_linux_virtual_machine" "main" {
  name                = "vm-${var.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  size                = var.vm_size
  admin_username      = var.admin_username
  tags                = var.tags

  network_interface_ids = [azurerm_network_interface.main.id]

  # Connexion par clé SSH uniquement (pas de mot de passe).
  disable_password_authentication = true
  admin_ssh_key {
    username   = var.admin_username
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  # Script exécuté au premier démarrage : installe Docker et lance la pipeline.
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    admin_username    = var.admin_username
    repo_url          = var.repo_url
    postgres_password = var.postgres_password
    s3_secret_key     = var.s3_secret_key
  }))
}

# --- Stockage ---------------------------------------------------------------

resource "azurerm_storage_account" "main" {
  # Nom unique mondialement : 3 à 24 caractères, minuscules et chiffres uniquement.
  name                            = "st${var.prefix}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = var.tags
}

resource "azurerm_storage_container" "transactions" {
  name                  = "transactions"
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}
