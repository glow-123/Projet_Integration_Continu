# Infrastructure de production (Terraform / OpenTofu sur Azure)

Ce dossier décrit en code l'environnement de production : réseau, pare-feu, VM Ubuntu
(qui lance la pipeline avec `docker-compose.prod.yml`) et un compte de stockage Azure.

## Déployer (depuis Azure Cloud Shell, Bash)

```bash
git clone https://github.com/glow-123/Projet_Integration_Continu.git
cd Projet_Integration_Continu/infra
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519      # une seule fois
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
cp terraform.tfvars.example terraform.tfvars && nano terraform.tfvars
terraform init
terraform plan
terraform apply
```

## Vérifier

```bash
ssh azureuser@$(terraform output -raw vm_public_ip)
docker compose -p pipeline-prod -f /opt/app/pipeline-data/docker-compose.prod.yml ps
```

## Tout supprimer (pour ne pas consommer le crédit)

```bash
terraform destroy
```
