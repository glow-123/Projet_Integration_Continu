"""Niveau 2 : stockage S3 (RustFS via docker-compose) -> traitement -> base."""
from decimal import Decimal

import pytest

import s3_storage
from generate_csv import generate_files
from pipeline import PipelineAborted, run_pipeline


def run_s3(tmp_path, conn, s3, **kwargs):
    client, bucket = s3
    kwargs.setdefault("sleep", lambda s: None)
    return run_pipeline(tmp_path, conn, source="s3", s3_client=client, bucket=bucket, **kwargs)


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_bucket_creation_is_idempotent(s3):
    client, bucket = s3
    s3_storage.ensure_bucket(client, bucket)  # déjà créé par la fixture : pas d'erreur
    assert bucket in [b["Name"] for b in client.list_buckets()["Buckets"]]


def test_upload_and_verify_files_in_bucket(s3, tmp_path):
    client, bucket = s3
    keys = s3_storage.upload_files(client, bucket, generate_files(tmp_path, 3, seed=42))
    assert s3_storage.missing_keys(client, bucket, keys) == []
    assert s3_storage.list_csv_keys(client, bucket) == sorted(keys)
    assert s3_storage.missing_keys(client, bucket, ["incoming/absent.csv"]) == ["incoming/absent.csv"]


def test_pipeline_generates_uploads_and_inserts_from_s3(conn, s3, tmp_path):
    report = run_s3(tmp_path, conn, s3, generate=True, n_files=3, seed=42)
    assert len(report["inserted"]) == 3
    assert count(conn, "processed_files") == 3
    flags = dict(conn.execute(
        "SELECT montant, flag FROM transactions WHERE montant IN (6200, 5000)").fetchall())
    assert flags == {Decimal("6200.00"): True, Decimal("5000.00"): False}


def test_processing_does_not_read_local_disk(conn, s3, tmp_path):
    client, bucket = s3
    paths = generate_files(tmp_path, 3, seed=42)
    s3_storage.upload_files(client, bucket, paths)
    for p in paths:
        p.unlink()  # plus aucun CSV local : tout doit venir du S3
    report = run_s3(tmp_path, conn, s3, generate=False)
    assert len(report["inserted"]) == 3


def test_no_double_processing_from_s3(conn, s3, tmp_path):
    client, bucket = s3
    run_s3(tmp_path, conn, s3, generate=True, n_files=3, seed=42)
    rows = count(conn, "transactions")

    # Même contenu ré-envoyé sous un autre nom : détecté grâce au hash
    client.copy_object(Bucket=bucket, Key="incoming/copie.csv",
                       CopySource={"Bucket": bucket, "Key": "incoming/transactions_001.csv"})
    report = run_s3(tmp_path, conn, s3, generate=False)
    assert report["inserted"] == [] and len(report["skipped"]) == 4
    assert count(conn, "transactions") == rows


def test_s3_download_succeeds_after_temporary_failures(conn, s3, tmp_path, capsys):
    waits = []
    report = run_s3(tmp_path, conn, s3, generate=True, n_files=3, seed=42,
                    simulate_s3_failures=2, max_attempts=3, retry_delay=0.5, sleep=waits.append)
    assert len(report["inserted"]) == 3
    assert waits == [0.5, 1.0]
    assert "récupération S3" in capsys.readouterr().err


def test_s3_download_stops_cleanly_when_file_stays_unavailable(conn, s3, tmp_path):
    with pytest.raises(PipelineAborted, match="récupération S3 de incoming/transactions_001.csv"):
        run_s3(tmp_path, conn, s3, generate=True, n_files=3, seed=42,
               simulate_s3_failures=99, max_attempts=3)
    assert count(conn, "processed_files") == 0

    # S3 de nouveau accessible : tout est traité au lancement suivant
    report = run_s3(tmp_path, conn, s3, generate=False)
    assert len(report["inserted"]) == 3
