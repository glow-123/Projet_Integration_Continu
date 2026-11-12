# Pipeline de transactions bancaires — Intégration et déploiement continus

Projet EFREI M2 Data Engineering & IA — **Gloria Amini, Mohamad Khobaiz**.

Des fichiers CSV de transactions bancaires sont générés, déposés dans un stockage S3,
puis la pipeline les **charge, valide, traite** et range le résultat dans **PostgreSQL**.
Chaque modification du code est **testée automatiquement** (GitHub Actions) puis
**déployée automatiquement** sur une machine virtuelle avec Docker.
L'infrastructure de production est aussi décrite en code avec **Terraform** (Azure).

Niveaux réalisés : **niveau 1**, **niveau 2**, et au **niveau 3** les options
**1 (déploiement continu sur VM avec Docker)** et **4 (Terraform)**.

---

## Architecture

```
generate_csv ──> S3 (RustFS) ──> chargement + validation ──> traitement ──> PostgreSQL
                     ▲                (loader.py)            (processing.py)   (db.py)
                     └───────────── retry (retry.py) sur le S3 et sur la base ─────┘
```

| Fichier | Rôle |
|---|---|
| `pipeline-data/src/generate_csv.py` | Génère des CSV de transactions (graine fixe → reproductible) |
| `pipeline-data/src/loader.py` | Lit et **valide** un CSV (colonnes, montants, encodage) |
| `pipeline-data/src/processing.py` | **Fonctions pures** : totaux envoyés par IBAN / par banque, reçus par IBAN, flag `montant > 5000` |
| `pipeline-data/src/s3_storage.py` | Bucket, envoi, vérification, listing et téléchargement S3 |
| `pipeline-data/src/db.py` | Schéma, insertion **tout-ou-rien**, anti-doublon par **SHA-256** |
| `pipeline-data/src/retry.py` | Retry générique : attente qui double, nombre max d'essais, erreurs affichées |
| `pipeline-data/src/pipeline.py` | Orchestration + ligne de commande |
| `pipeline-data/sql/schema.sql` | Tables `processed_files`, `transactions`, `total_sent_by_iban`, `total_sent_by_bank`, `total_received_by_iban` |
| `pipeline-data/docker-compose.yml` | PostgreSQL 16 + S3 local (dev / CI) |
| `pipeline-data/docker-compose.prod.yml` + `Dockerfile` | Production : PostgreSQL + S3 + pipeline en boucle |
| `infra/` | Terraform : réseau, pare-feu, VM Ubuntu, compte de stockage Azure |

**Pourquoi RustFS et pas MinIO ?** MinIO ne publie plus d'images Docker gratuites
(téléchargement refusé sur Docker Hub et quay.io). RustFS est un S3 compatible, cité
dans le sujet ; le code utilise l'API S3 standard (boto3), donc rien d'autre ne change.

## Fiabilité

- **Tout ou rien** : un fichier est inséré dans une seule transaction SQL ; si une ligne échoue, rien n'est écrit (rollback).
- **Anti-doublon** : chaque fichier a une empreinte SHA-256 (colonne `UNIQUE`). Un fichier déjà traité — même renommé — est ignoré.
- **Retry** : si la base ou le S3 est indisponible, nouvelle tentative avec une attente qui double (0,5 s, 1 s, …) jusqu'à un maximum. Seules les erreurs temporaires sont réessayées ; la connexion à la base est rouverte si elle a été coupée.
- **Codes de sortie** : `0` succès, `1` au moins un fichier invalide, `2` pipeline arrêtée (trop d'échecs). Les fichiers non traités le seront au lancement suivant.

## Lancer en local

Prérequis : Docker et Python 3.12+.

```bash
cd pipeline-data
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows : .venv\Scripts\pip
docker compose up -d --wait            # PostgreSQL (5432) + S3 RustFS (9000, console 9001)
pytest -v                              # 34 tests
python src/pipeline.py --generate      # génère -> envoie au S3 -> traite -> base
python src/pipeline.py                 # relance : 0 inséré, tout est ignoré (déjà traité)
python src/pipeline.py --generate --files 4 --seed 7 --simulate-db-failures 2 --retry-delay 0.5   # démo du retry
python src/pipeline.py --simulate-s3-failures 5     # démo de l'arrêt propre (code 2)
docker compose down -v
```

Options utiles : `--source local --data-dir data` (niveau 1, sans S3), `--max-attempts`, `--retry-delay`.

## Tests (34)

- **Unitaires** : fonctions pures (totaux, flag strictement > 5000, cas limite 5000), chargement et validation des CSV, retry.
- **Intégration** avec une vraie base et un vrai S3 : insertion, valeurs, totaux comparés à un `SUM` SQL, tout-ou-rien, anti-doublon, lecture depuis le S3 uniquement.
- **Retry** : pannes simulées puis succès, arrêt propre après le maximum, vraie coupure de connexion PostgreSQL puis reconnexion.

En local, si un service est absent, les tests d'intégration sont **ignorés**.
En CI (`REQUIRE_SERVICES=1`), un service injoignable fait **échouer** la CI.

## Intégration continue — `.github/workflows/ci.yml`

À chaque push sur `main` et à chaque pull request :

1. démarre PostgreSQL et le S3 avec `docker compose` ;
2. lance les 34 tests ;
3. exécute la pipeline complète ;
4. la relance et vérifie qu'**aucun fichier n'est retraité** ;
5. démontre le **retry** (2 pannes simulées puis succès).

**Simulation d'échec** (PR #2) : seuil passé de 5000 à 500 → 4 tests en échec, CI rouge ;
seuil corrigé → CI verte.

## Déploiement continu (option 1) — `.github/workflows/deploy.yml`

Se déclenche **automatiquement quand la CI est verte sur `main`** (ou à la main) :
copie le code sur la VM par SSH, crée le `.env` depuis les **secrets GitHub**
(`VM_HOST`, `VM_USER`, `VM_PASSWORD`, `POSTGRES_PASSWORD`, `S3_SECRET_KEY`), puis
`docker compose -f docker-compose.prod.yml up -d --build`.
En production, la pipeline tourne en boucle (`deploy/scheduler.sh`, toutes les 60 s) ;
aucun port de la base ou du S3 n'est exposé.

Vérifier sur la VM :

```bash
docker compose -p pipeline-prod -f ~/pipeline/docker-compose.prod.yml ps
docker compose -p pipeline-prod -f ~/pipeline/docker-compose.prod.yml exec postgres psql -U pipeline -d pipeline -c "select count(*) from transactions;"
docker compose -p pipeline-prod -f ~/pipeline/docker-compose.prod.yml logs --tail 15 pipeline
```

## Infrastructure as Code (option 4) — `infra/`

Terraform décrit l'environnement de production sur Azure : groupe de ressources, réseau
et pare-feu (**seul le SSH est ouvert**), IP publique, **VM Ubuntu** qui installe Docker,
clone ce dépôt et lance `docker-compose.prod.yml` au premier démarrage (cloud-init), et
un **compte de stockage** avec un conteneur Blob. Les mots de passe sont des variables
`sensitive`, dans `terraform.tfvars` (ignoré par git).

Le workflow `.github/workflows/terraform.yml` exécute `fmt -check`, `init` et `validate`
à chaque pull request qui touche `infra/`. Instructions de déploiement : [`infra/README.md`](infra/README.md)
(`terraform init` / `plan` / `apply`, puis `terraform destroy` pour ne pas consommer de crédit).

**Déploiement réel (12/11/2026)** : `terraform apply` depuis Azure Cloud Shell sur une
souscription *Azure for Students* → **11 ressources créées** dans `rg-pipeline`
(région **Spain Central**, VM `Standard_B2s_v2` : France Central est interdite par la
politique de la souscription et `Standard_B2s` n'avait plus de capacité). Au premier
démarrage, la VM a installé Docker, cloné le dépôt et lancé les **3 conteneurs** ;
la pipeline a inséré **24 transactions**, puis ignore les fichiers déjà traités.
Après la présentation : `terraform destroy`.

## Pistes d'amélioration

OCR sur des images de relevés, extraction de transactions depuis du texte avec un petit
modèle de langage, passage sur Kubernetes.
