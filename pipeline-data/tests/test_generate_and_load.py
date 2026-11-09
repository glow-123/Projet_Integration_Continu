import csv
from decimal import Decimal

import pytest

from generate_csv import FIELDNAMES, generate_files
from loader import InvalidCsvError, load_csv
from processing import flag_large_transactions


def test_generates_files_with_5_to_10_transactions(tmp_path):
    paths = generate_files(tmp_path, n_files=5, seed=1)
    assert len(paths) == 5
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert 5 <= len(rows) <= 10
        assert list(rows[0].keys()) == FIELDNAMES


def test_generation_is_reproducible(tmp_path):
    a = generate_files(tmp_path / "a", seed=42)
    b = generate_files(tmp_path / "b", seed=42)
    for pa, pb in zip(a, b):
        assert pa.read_text(encoding="utf-8") == pb.read_text(encoding="utf-8")


def test_scenario_data_for_flags(tmp_path):
    """Le 1er fichier contient un 6200 (flaggé) et un 5000 pile (non flaggé)."""
    first = generate_files(tmp_path, seed=42)[0]
    flagged = flag_large_transactions(load_csv(first))
    by_amount = {t["montant"]: t["flag"] for t in flagged}
    assert by_amount[Decimal("6200.00")] is True
    assert by_amount[Decimal("5000.00")] is False


def test_loader_returns_typed_values(tmp_path):
    tx = load_csv(generate_files(tmp_path, seed=42)[0])
    assert isinstance(tx[0]["montant"], Decimal)


def test_loader_rejects_invalid_amount(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        ",".join(FIELDNAMES) + "\n2026-09-12 14:30:00,FR1,FR,B,DE1,DE,abc\n", encoding="utf-8"
    )
    with pytest.raises(InvalidCsvError):
        load_csv(bad)


def test_loader_rejects_missing_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("iban_origine,montant\nFR1,10\n", encoding="utf-8")
    with pytest.raises(InvalidCsvError):
        load_csv(bad)
