"""Tests d'intégration (niveau 1) : pipeline complète contre une vraie base PostgreSQL.

Base utilisée : $DATABASE_URL (défaut : celle du docker-compose). Fixture `conn` : conftest.py.
"""
import csv
from decimal import Decimal

import pytest

import db
from generate_csv import generate_files
from loader import load_csv
from pipeline import run_pipeline
from processing import process


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_pipeline_inserts_all_transactions(conn, tmp_path):
    report = run_pipeline(tmp_path, conn, generate=True, n_files=3, seed=42)
    assert len(report["inserted"]) == 3 and not report["failed"]

    expected_rows = 0
    for path in sorted(tmp_path.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            expected_rows += len(list(csv.DictReader(f)))
    assert count(conn, "processed_files") == 3
    assert count(conn, "transactions") == expected_rows


def test_stored_values_match_csv(conn, tmp_path):
    run_pipeline(tmp_path, conn, generate=True, n_files=1, seed=42)
    first = sorted(tmp_path.glob("*.csv"))[0]
    with open(first, newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))

    db_rows = conn.execute(
        "SELECT iban_origine, iban_destinataire, banque_source, montant "
        "FROM transactions ORDER BY id"
    ).fetchall()
    assert [(r["iban_origine"], r["iban_destinataire"], r["banque_source"], Decimal(r["montant"]))
            for r in csv_rows] == db_rows


def test_stored_totals_match_processing(conn, tmp_path):
    run_pipeline(tmp_path, conn, generate=True, n_files=1, seed=42)
    expected = process(load_csv(sorted(tmp_path.glob("*.csv"))[0]))

    for table, column, key in (
        ("total_sent_by_iban", "iban", "sent_by_iban"),
        ("total_sent_by_bank", "banque", "sent_by_bank"),
        ("total_received_by_iban", "iban", "received_by_iban"),
    ):
        stored = dict(conn.execute(f"SELECT {column}, total FROM {table}").fetchall())
        assert stored == expected[key], table


def test_totals_consistent_with_stored_transactions(conn, tmp_path):
    """Les totaux en base = SUM recalculé en SQL sur les transactions en base."""
    run_pipeline(tmp_path, conn, generate=True, n_files=3, seed=42)
    mismatches = conn.execute(
        "SELECT t.file_id, t.iban FROM total_sent_by_iban t "
        "JOIN (SELECT file_id, iban_origine, SUM(montant) s FROM transactions "
        "      GROUP BY file_id, iban_origine) x "
        "  ON x.file_id = t.file_id AND x.iban_origine = t.iban "
        "WHERE x.s <> t.total"
    ).fetchall()
    assert mismatches == []


def test_flags_are_correct(conn, tmp_path):
    run_pipeline(tmp_path, conn, generate=True, n_files=3, seed=42)
    flags = dict(conn.execute(
        "SELECT montant, flag FROM transactions WHERE montant IN (6200, 5000)"
    ).fetchall())
    assert flags == {Decimal("6200.00"): True, Decimal("5000.00"): False}
    wrong = conn.execute(
        "SELECT count(*) FROM transactions WHERE flag <> (montant > 5000)"
    ).fetchone()[0]
    assert wrong == 0


def test_same_file_is_not_processed_twice(conn, tmp_path):
    first = run_pipeline(tmp_path, conn, generate=True, n_files=3, seed=42)
    rows_after_first = count(conn, "transactions")
    second = run_pipeline(tmp_path, conn, generate=False)

    assert len(first["inserted"]) == 3
    assert second["inserted"] == [] and len(second["skipped"]) == 3
    assert count(conn, "transactions") == rows_after_first


def test_insert_is_all_or_nothing(conn, tmp_path):
    """Une erreur au milieu de l'insertion => rien n'est enregistré, fichier non marqué."""
    path = generate_files(tmp_path, n_files=1, seed=42)[0]
    result = process(load_csv(path))
    result["transactions"][-1] = {**result["transactions"][-1], "pays_source": "FRANCE"}  # > CHAR(2)

    with pytest.raises(db.PermanentDbError, match="rollback"):
        db.insert_processed_file(conn, path.name, db.file_hash(path), result)
    assert count(conn, "processed_files") == 0
    assert count(conn, "transactions") == 0
