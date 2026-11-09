import copy
from datetime import datetime
from decimal import Decimal

from processing import (
    flag_large_transactions,
    process,
    total_received_by_iban,
    total_sent_by_bank,
    total_sent_by_iban,
)


def make(origin, bank, dest, amount):
    return {
        "datetime_transaction": datetime(2026, 9, 12, 14, 30),
        "iban_origine": origin,
        "pays_source": "FR",
        "banque_source": bank,
        "iban_destinataire": dest,
        "pays_destinataire": "DE",
        "montant": Decimal(str(amount)),
    }


# Jeu de test écrit à la main : les résultats attendus se calculent de tête
TX = [
    make("A", "Banque1", "C", 100),
    make("A", "Banque1", "D", 50.50),
    make("B", "Banque2", "C", 6200),
    make("B", "Banque2", "D", 5000),
]


def test_total_sent_by_iban():
    assert total_sent_by_iban(TX) == {"A": Decimal("150.50"), "B": Decimal("11200")}


def test_total_sent_by_bank():
    assert total_sent_by_bank(TX) == {"Banque1": Decimal("150.50"), "Banque2": Decimal("11200")}


def test_total_received_by_iban():
    assert total_received_by_iban(TX) == {"C": Decimal("6300"), "D": Decimal("5050.50")}


def test_flag_strictly_greater_than_5000():
    flagged = flag_large_transactions(TX)
    assert [t["flag"] for t in flagged] == [False, False, True, False]  # 5000 pile = pas de flag


def test_empty_input():
    assert total_sent_by_iban([]) == {}
    assert flag_large_transactions([]) == []


def test_functions_do_not_modify_input():
    before = copy.deepcopy(TX)
    process(TX)
    assert TX == before
    assert all("flag" not in t for t in TX)


def test_same_input_same_output():
    assert process(TX) == process(TX)
