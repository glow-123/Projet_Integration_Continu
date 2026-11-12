variable "location" {
  description = "Région Azure. Si Azure refuse (RequestDisallowedByAzure), essaie une autre région autorisée pour ta souscription étudiante."
  type        = string
  default     = "francecentral"
}

variable "prefix" {
  description = "Préfixe utilisé pour nommer toutes les ressources."
  type        = string
  default     = "pipeline"
}

variable "vm_size" {
  description = "Taille de la VM. Si indisponible dans ta région/souscription, essaie Standard_B2s_v2 ou Standard_D2s_v3."
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "Utilisateur administrateur de la VM."
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Chemin de ta clé publique SSH (créée avec `ssh-keygen -t ed25519`)."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_allowed_cidr" {
  description = "Adresse IP (ou plage) autorisée à se connecter en SSH, ex: \"82.12.34.56/32\". \"*\" = tout le monde (déconseillé)."
  type        = string
  default     = "*"
}

variable "repo_url" {
  description = "Dépôt Git cloné par la VM au démarrage (doit être public)."
  type        = string
  default     = "https://github.com/glow-123/Projet_Integration_Continu.git"
}

variable "postgres_password" {
  description = "Mot de passe PostgreSQL de la pipeline (jamais écrit dans git)."
  type        = string
  sensitive   = true
}

variable "s3_secret_key" {
  description = "Clé secrète du stockage S3 (RustFS) de la pipeline (jamais écrite dans git)."
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Étiquettes ajoutées à toutes les ressources."
  type        = map(string)
  default = {
    project = "integration-continue"
    managed = "terraform"
  }
}
