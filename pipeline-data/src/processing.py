"""TRAITEMENT des données : uniquement des fonctions PURES.

Une fonction pure :
  - ne modifie pas ses entrées,
  - ne dépend d'aucun état externe (pas d'heure, de fichier, de variable globale),
  - renvoie toujours le même résultat pour les mêmes entrées.
"""
from decimal import Decimal

FLAG_THRESHOLD = Decimal("500")


def _sum_by(transactions, group_key):
    totals = {}
    for t in transactions:
        key = t[group_key]
        totals[key] = totals.get(key, Decimal("0")) + t["montant"]
    return totals


def total_sent_by_iban(transactions):
    """Somme des montants envoyés, par iban_origine."""
    return _sum_by(transactions, "iban_origine")


def total_sent_by_bank(transactions):
    """Somme des montants envoyés, par banque_source."""
    return _sum_by(transactions, "banque_source")


def total_received_by_iban(transactions):
    """Somme des montants reçus, par iban_destinataire."""
    return _sum_by(transactions, "iban_destinataire")


def flag_large_transactions(transactions, threshold=FLAG_THRESHOLD):
    """Renvoie de NOUVELLES transactions avec un champ 'flag'.

    flag = True si montant strictement supérieur au seuil (5000 par défaut).
    Les transactions d'entrée ne sont pas modifiées.
    """
    return [{**t, "flag": t["montant"] > threshold} for t in transactions]


def process(transactions):
    """Applique tous les traitements et renvoie un résultat structuré."""
    return {
        "sent_by_iban": total_sent_by_iban(transactions),
        "sent_by_bank": total_sent_by_bank(transactions),
        "received_by_iban": total_received_by_iban(transactions),
        "transactions": flag_large_transactions(transactions),
    }
