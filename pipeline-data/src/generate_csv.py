"""Génération de fichiers CSV de transactions financières.

Les données ne sont PAS totalement aléatoires : un jeu de comptes fixe est
réutilisé (donc des IBAN et des banques reviennent), et des transactions
"scénario" sont injectées pour pouvoir vérifier les traitements :
  - une transaction à 6200 (> 5000)  -> doit être flaguée
  - une transaction à exactement 5000 -> ne doit PAS être flaguée (strictement supérieur)
Le générateur est reproductible grâce à une graine (seed).
"""
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

FIELDNAMES = [
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
]

# (iban, pays, banque) : jeu fixe pour que les mêmes comptes reviennent
ACCOUNTS = [
    ("FR7630006000011234567890189", "FR", "BNP Paribas"),
    ("FR7612345678901234567890123", "FR", "BNP Paribas"),
    ("FR7630004000031234567890143", "FR", "Societe Generale"),
    ("DE89370400440532013000", "DE", "Deutsche Bank"),
    ("ES9121000418450200051332", "ES", "Santander"),
    ("IT60X0542811101000000123456", "IT", "UniCredit"),
]

START = datetime(2026, 9, 12, 14, 30, 0)


def _transaction(rng, when, origin, dest, amount):
    return {
        "datetime_transaction": when.isoformat(sep=" "),
        "iban_origine": origin[0],
        "pays_source": origin[1],
        "banque_source": origin[2],
        "iban_destinataire": dest[0],
        "pays_destinataire": dest[1],
        "montant": f"{amount:.2f}",
    }


def build_transactions(rng, count, file_index=0):
    """Construit `count` transactions. Ne dépend que de rng et des arguments."""
    rows = []
    for i in range(count):
        origin, dest = rng.sample(ACCOUNTS, 2)  # émetteur != destinataire
        when = START + timedelta(days=file_index, minutes=17 * i)
        amount = round(rng.uniform(10, 4500), 2)
        rows.append(_transaction(rng, when, origin, dest, amount))

    # Transactions "scénario" pour tester les flags (placées dans le 1er fichier)
    if file_index == 0 and count >= 2:
        rows[0] = _transaction(rng, START, ACCOUNTS[0], ACCOUNTS[3], 6200.00)
        rows[1] = _transaction(rng, START + timedelta(minutes=17), ACCOUNTS[2], ACCOUNTS[4], 5000.00)
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def generate_files(output_dir, n_files=3, seed=42):
    """Génère n_files CSV de 5 à 10 transactions. Retourne la liste des chemins."""
    rng = random.Random(seed)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(n_files):
        count = rng.randint(5, 10)
        rows = build_transactions(rng, count, file_index=index)
        path = output_dir / f"transactions_{index + 1:03d}.csv"
        write_csv(path, rows)
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Génère des CSV de transactions")
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--files", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    for p in generate_files(args.output_dir, args.files, args.seed):
        print(f"Fichier généré : {p}")


if __name__ == "__main__":
    main()
