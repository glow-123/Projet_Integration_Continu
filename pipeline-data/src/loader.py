"""CHARGEMENT des données (lecture + validation du format).

Ce module ne fait aucun calcul métier : il lit un CSV et renvoie des
transactions propres (montant en Decimal, date en datetime). Les calculs
sont dans processing.py (fonctions pures), conformément à l'énoncé.
"""
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED_COLUMNS = [
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
]


class InvalidCsvError(ValueError):
    """Le fichier CSV ne respecte pas le format attendu."""


def load_csv(path):
    """Charge un fichier CSV local et renvoie une liste de transactions (dict)."""
    path = Path(path)
    return load_csv_bytes(path.read_bytes(), path.name)


def load_csv_bytes(content, name):
    """Charge un CSV depuis son contenu brut (ex : objet téléchargé depuis le S3)."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidCsvError(f"{name}: encodage invalide (UTF-8 attendu)")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise InvalidCsvError(f"{name}: colonnes manquantes {missing}")

    transactions = []
    for line_no, row in enumerate(reader, start=2):  # ligne 1 = en-tête
        transactions.append(_parse_row(row, name, line_no))
    if not transactions:
        raise InvalidCsvError(f"{name}: fichier vide")
    return transactions


def _parse_row(row, filename, line_no):
    try:
        montant = Decimal(row["montant"])
    except (InvalidOperation, TypeError):
        raise InvalidCsvError(f"{filename} ligne {line_no}: montant invalide {row['montant']!r}")
    if montant < 0:
        raise InvalidCsvError(f"{filename} ligne {line_no}: montant négatif {montant}")
    try:
        when = datetime.fromisoformat(row["datetime_transaction"])
    except (ValueError, TypeError):
        raise InvalidCsvError(
            f"{filename} ligne {line_no}: date invalide {row['datetime_transaction']!r}"
        )
    for col in ("iban_origine", "iban_destinataire", "banque_source"):
        if not row[col]:
            raise InvalidCsvError(f"{filename} ligne {line_no}: champ vide {col}")
    return {**row, "montant": montant, "datetime_transaction": when}
