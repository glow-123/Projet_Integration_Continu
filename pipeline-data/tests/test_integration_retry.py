"""Retry à l'insertion en base : panne simulée, vraie coupure, arrêt propre, pas de doublon."""
import pytest

import db
from pipeline import PipelineAborted, run_pipeline


def count(table):
    with db.get_connection() as c:  # connexion neuve : celle du test a pu être coupée
        return c.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_insert_succeeds_after_temporary_failures(conn, tmp_path):
    waits = []
    report = run_pipeline(tmp_path, conn, generate=True, n_files=3, seed=42,
                          simulate_db_failures=2, max_attempts=3, retry_delay=0.5,
                          sleep=waits.append)
    assert len(report["inserted"]) == 3
    assert waits == [0.5, 1.0]  # 2 échecs -> 2 attentes (backoff x2), puis succès
    assert count("processed_files") == 3  # aucun doublon malgré les retries


def test_pipeline_stops_after_max_attempts(conn, tmp_path, capsys):
    with pytest.raises(PipelineAborted, match="insertion en base.*3 tentative") as info:
        run_pipeline(tmp_path, conn, generate=True, n_files=3, seed=42,
                     simulate_db_failures=10, max_attempts=3, sleep=lambda s: None)
    assert info.value.report["inserted"] == []
    assert "panne simulée" in capsys.readouterr().err  # erreurs affichées clairement
    assert count("processed_files") == 0  # rien n'a été marqué comme traité

    # Panne terminée : le prochain lancement traite tout, une seule fois
    report = run_pipeline(tmp_path, conn, generate=False)
    assert len(report["inserted"]) == 3


def test_real_connection_loss_reconnects(conn, tmp_path, monkeypatch):
    """La connexion est réellement coupée côté serveur juste avant l'insertion."""
    original = db.is_processed
    killed = []

    def is_processed_then_cut(c, digest):
        result = original(c, digest)
        if not killed:
            with db.get_connection() as admin:
                admin.execute("SELECT pg_terminate_backend(%s)", (c.info.backend_pid,))
            killed.append(True)
        return result

    monkeypatch.setattr(db, "is_processed", is_processed_then_cut)
    reconnections = []

    def reconnect():
        reconnections.append(1)
        monkeypatch.setattr(db, "is_processed", original)
        return db.get_connection()

    report = run_pipeline(tmp_path, conn, generate=True, n_files=3, seed=42,
                          reconnect=reconnect, sleep=lambda s: None)
    assert len(report["inserted"]) == 3
    assert reconnections == [1]
    assert count("processed_files") == 3
