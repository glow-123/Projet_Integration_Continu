"""STOCKAGE S3 : bucket, envoi des CSV, vérification et récupération.

Compatible avec tout service S3 (RustFS en local via docker-compose).
Configuration par variables d'environnement :
  S3_ENDPOINT_URL (défaut http://localhost:9000), S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET
"""
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

DEFAULT_BUCKET = "transactions"
PREFIX = "incoming/"

# Erreurs réseau / service indisponible : temporaires, donc à retenter
TRANSIENT_S3_ERRORS = (
    EndpointConnectionError,
    ConnectTimeoutError,
    ReadTimeoutError,
    ConnectionClosedError,
)


class S3ObjectNotFound(RuntimeError):
    """Le fichier n'existe pas dans le bucket (erreur définitive)."""


def get_client(endpoint_url=None):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "pipeline"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "pipeline-secret"),
        region_name="us-east-1",
        # Pas de retry caché dans boto3 : c'est notre mécanisme (retry.py) qui s'en charge
        config=Config(retries={"max_attempts": 1, "mode": "standard"},
                      connect_timeout=3, read_timeout=5),
    )


def bucket_name():
    return os.environ.get("S3_BUCKET", DEFAULT_BUCKET)


def ensure_bucket(client, bucket):
    """Crée le bucket s'il n'existe pas (idempotent)."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
            raise
        client.create_bucket(Bucket=bucket)


def upload_files(client, bucket, paths, prefix=PREFIX):
    """Envoie les fichiers locaux dans le bucket. Renvoie les clés S3."""
    keys = []
    for path in paths:
        path = Path(path)
        key = f"{prefix}{path.name}"
        client.upload_file(str(path), bucket, key)
        keys.append(key)
    return keys


def missing_keys(client, bucket, keys):
    """Renvoie les clés absentes du bucket (liste vide = tout est bien présent)."""
    present = set(list_csv_keys(client, bucket, prefix=""))
    return [k for k in keys if k not in present]


def list_csv_keys(client, bucket, prefix=PREFIX):
    keys = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []) if obj["Key"].endswith(".csv"))
    return sorted(keys)


def download(client, bucket, key):
    """Récupère le contenu brut d'un fichier du bucket (bytes)."""
    try:
        return client.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise S3ObjectNotFound(f"{key} introuvable dans le bucket {bucket}") from exc
        raise
