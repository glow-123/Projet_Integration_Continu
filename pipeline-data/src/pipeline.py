"""PIPELINE complète.

Flux (niveau 2, par défaut) :
    génération CSV -> envoi dans le S3 -> vérification
    S3 -> récupération (retry) -> chargement -> traitement -> base (retry)

Usage :
    python src/pipeline.py --generate                 # génère, envoie au S3, traite
    python src/pipeline.py                            # traite ce qui est dans le S3
    python src/pipeline.py --source local --data-dir data   # niveau 1 : disque local
    python src/pipeline.py --generate --simulate-db-failures 2   # démo du retry base
    python src/pipeline.py --simulate-s3-failures 5              # démo arrêt propre

Les fichiers déjà traités (même contenu, hash SHA-256) ne sont jamais retraités.
Codes de sortie : 0 = OK, 1 = au moins un fichier invalide, 2 = pipeline arrêtée
(nombre maximal de tentatives dépassé).
"""
import argparse
import sys
import time
from pathlib import Path

from botocore.exceptions import EndpointConnectionError

import db
import s3_storage
from generate_csv import generate_files
from loader import InvalidCsvError, load_csv_bytes
from processing import process
from retry import RetryError, fail_first_calls, retry


class PipelineAborted(RuntimeError):
    """Arrêt de la pipeline : une ressource reste indisponible malgré les retries."""

    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def run_pipeline(data_dir, conn, generate=False, n_files=3, seed=42, *, source="local",
                 s3_client=None, bucket=None, reconnect=None, max_attempts=3,
                 retry_delay=1.0, simulate_db_failures=0, simulate_s3_failures=0,
                 sleep=time.sleep):
    """Exécute la pipeline et renvoie un bilan {inserted, skipped, failed}."""
    data_dir = Path(data_dir)
    report = {"inserted": [], "skipped": [], "failed": []}

    def with_retry(func, label, retry_on):
        try:
            return retry(func, label=label, retry_on=retry_on, max_attempts=max_attempts,
                         delay=retry_delay, sleep=sleep)
        except RetryError as exc:
            raise PipelineAborted(f"Pipeline arrêtée — {exc}", report) from exc

    # 1. Génération (+ envoi dans le S3 au niveau 2)
    generated = []
    if generate:
        generated = generate_files(data_dir, n_files, seed)
        for p in generated:
            print(f"[generate] {p}")

    if source == "s3":
        transient = s3_storage.TRANSIENT_S3_ERRORS
        with_retry(lambda: s3_storage.ensure_bucket(s3_client, bucket),
                   f"connexion au S3 / bucket {bucket}", transient)
        print(f"[s3] bucket '{bucket}' prêt")
        if generated:
            keys = s3_storage.upload_files(s3_client, bucket, generated)
            missing = s3_storage.missing_keys(s3_client, bucket, keys)
            if missing:
                raise PipelineAborted(f"Fichiers absents du S3 après envoi : {missing}", report)
            print(f"[s3] {len(keys)} fichier(s) envoyé(s) et vérifié(s) dans le bucket")

        download = s3_storage.download
        if simulate_s3_failures:
            download = fail_first_calls(download, simulate_s3_failures, lambda: EndpointConnectionError(
                endpoint_url="http://s3 (panne simulée)"))
        items = [
            (key.rsplit("/", 1)[-1],
             lambda key=key: with_retry(lambda: download(s3_client, bucket, key),
                                        f"récupération S3 de {key}", transient))
            for key in s3_storage.list_csv_keys(s3_client, bucket)
        ]
    else:
        items = [(p.name, p.read_bytes) for p in sorted(data_dir.glob("*.csv"))]

    # 2. Base de données
    db.init_schema(conn)
    print("[db] schéma prêt")

    state = {"conn": conn}
    insert = db.insert_processed_file
    if simulate_db_failures:
        insert = fail_first_calls(insert, simulate_db_failures, lambda: db.TransientDbError(
            "connexion à la base perdue (panne simulée)"))

    def insert_attempt(name, digest, result):
        if state["conn"].closed and reconnect:  # connexion perdue : on en rouvre une
            print("[db] reconnexion à la base", file=sys.stderr)
            state["conn"] = reconnect()
        return insert(state["conn"], name, digest, result)

    # 3. Récupération -> chargement -> traitement -> insertion, fichier par fichier
    for name, fetch in items:
        try:
            content = fetch()  # une indisponibilité persistante lève PipelineAborted
        except s3_storage.S3ObjectNotFound as exc:  # supprimé entre le listing et la lecture
            print(f"[error] {exc}", file=sys.stderr)
            report["failed"].append(name)
            continue
        digest = db.content_hash(content)
        if db.is_processed(state["conn"], digest):
            print(f"[skip] {name} déjà traité")
            report["skipped"].append(name)
            continue
        try:
            result = process(load_csv_bytes(content, name))
            file_id = with_retry(lambda: insert_attempt(name, digest, result),
                                 f"insertion en base de {name}", (db.TransientDbError,))
        except (InvalidCsvError, db.PermanentDbError) as exc:
            print(f"[error] {exc}", file=sys.stderr)
            report["failed"].append(name)
            continue
        if file_id is None:  # inséré entre-temps (ex : tentative précédente validée)
            print(f"[skip] {name} déjà traité")
            report["skipped"].append(name)
        else:
            print(f"[insert] {name} : {len(result['transactions'])} transactions (id={file_id})")
            report["inserted"].append(name)
    return report


def main():
    parser = argparse.ArgumentParser(description="Pipeline CSV/S3 -> PostgreSQL")
    parser.add_argument("--generate", action="store_true", help="générer les CSV avant traitement")
    parser.add_argument("--source", choices=["s3", "local"], default="s3")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--files", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=1.0, help="secondes (x2 à chaque essai)")
    parser.add_argument("--simulate-db-failures", type=int, default=0,
                        help="fait échouer les N premières insertions (démo du retry)")
    parser.add_argument("--simulate-s3-failures", type=int, default=0,
                        help="fait échouer les N premières récupérations S3 (démo du retry)")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # logs dans l'ordre, même redirigés (CI)

    s3_client = s3_storage.get_client() if args.source == "s3" else None
    reconnect = lambda: db.get_connection(args.database_url)  # noqa: E731
    try:
        with db.get_connection(args.database_url) as conn:
            report = run_pipeline(
                args.data_dir, conn, args.generate, args.files, args.seed,
                source=args.source, s3_client=s3_client, bucket=s3_storage.bucket_name(),
                reconnect=reconnect, max_attempts=args.max_attempts, retry_delay=args.retry_delay,
                simulate_db_failures=args.simulate_db_failures,
                simulate_s3_failures=args.simulate_s3_failures,
            )
    except PipelineAborted as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        r = exc.report
        print(f"Bilan partiel : {len(r['inserted'])} inséré(s), {len(r['skipped'])} ignoré(s), "
              f"{len(r['failed'])} en échec. Les fichiers non traités le seront au prochain lancement.",
              file=sys.stderr)
        return 2

    print(
        f"Bilan : {len(report['inserted'])} inséré(s), "
        f"{len(report['skipped'])} ignoré(s), {len(report['failed'])} en échec"
    )
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
