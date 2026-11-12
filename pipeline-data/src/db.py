"""ACCÈS à la base PostgreSQL : schéma, anti-doublons et insertion.

L'insertion d'un fichier se fait "tout ou rien" dans UNE transaction SQL :
soit le fichier, ses transactions et ses totaux sont tous enregistrés,
soit rien ne l'est (rollback). Un fichier n'est marqué comme traité
(table processed_files) que si toute l'insertion a réussi.
"""
import hashlib
import os
from pathlib import Path

import psycopg

DEFAULT_DATABASE_URL = "postgresql://pipeline:pipeline@localhost:5432/pipeline"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


class TransientDbError(RuntimeError):
    """Erreur temporaire (connexion perdue, base indisponible...) : à retenter."""


class PermanentDbError(RuntimeError):
    """Erreur définitive (donnée refusée par la base...) : inutile de retenter."""


def get_connection(database_url=None):
    """Ouvre une connexion (URL : argument, sinon $DATABASE_URL, sinon défaut local)."""
    url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    # autocommit + blocs conn.transaction() explicites = transactions bien délimitées
    return psycopg.connect(url, autocommit=True)


def init_schema(conn, schema_path=SCHEMA_PATH):
    """Crée les tables si elles n'existent pas encore (idempotent)."""
    conn.execute(Path(schema_path).read_text(encoding="utf-8"))


def content_hash(content):
    """SHA-256 du contenu : identifie un fichier même s'il est renommé."""
    return hashlib.sha256(content).hexdigest()


def file_hash(path):
    return content_hash(Path(path).read_bytes())


def is_processed(conn, digest):
    row = conn.execute("SELECT 1 FROM processed_files WHERE file_hash = %s", (digest,)).fetchone()
    return row is not None


def insert_processed_file(conn, filename, digest, result):
    """Insère un fichier traité (résultat de processing.process) en tout ou rien.

    Renvoie l'id du fichier, ou None s'il avait déjà été traité.
    """
    try:
        with conn.transaction():
            row = conn.execute(
                "INSERT INTO processed_files (filename, file_hash, nb_rows) VALUES (%s, %s, %s) "
                "ON CONFLICT (file_hash) DO NOTHING RETURNING id",
                (filename, digest, len(result["transactions"])),
            ).fetchone()
            if row is None:  # déjà traité (éventuellement par un autre process)
                return None
            file_id = row[0]

            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO transactions (file_id, datetime_transaction, iban_origine, "
                    "pays_source, banque_source, iban_destinataire, pays_destinataire, montant, flag) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            file_id,
                            t["datetime_transaction"],
                            t["iban_origine"],
                            t["pays_source"],
                            t["banque_source"],
                            t["iban_destinataire"],
                            t["pays_destinataire"],
                            t["montant"],
                            t["flag"],
                        )
                        for t in result["transactions"]
                    ],
                )
                for table, column, totals in (
                    ("total_sent_by_iban", "iban", result["sent_by_iban"]),
                    ("total_sent_by_bank", "banque", result["sent_by_bank"]),
                    ("total_received_by_iban", "iban", result["received_by_iban"]),
                ):
                    cur.executemany(
                        f"INSERT INTO {table} (file_id, {column}, total) VALUES (%s, %s, %s)",
                        [(file_id, key, total) for key, total in totals.items()],
                    )
            return file_id
    except psycopg.OperationalError as exc:
        # Connexion perdue, base redémarrée, deadlock... : rien n'a été validé, on peut retenter
        raise TransientDbError(f"insertion de {filename} interrompue (rollback) : {exc}") from exc
    except psycopg.Error as exc:
        # La transaction a déjà été annulée par le bloc conn.transaction()
        raise PermanentDbError(f"Échec de l'insertion de {filename} (rollback effectué) : {exc}") from exc
