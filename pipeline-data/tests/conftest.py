"""Fixtures partagées : vraie base PostgreSQL et vrai service S3 (docker-compose).

En local, si un service est injoignable, les tests qui en ont besoin sont ignorés.
En CI, REQUIRE_SERVICES=1 : un service injoignable fait ÉCHOUER les tests.
"""
import os
import uuid

import psycopg
import pytest
from botocore.exceptions import BotoCoreError, ClientError

import db
import s3_storage


def _unavailable(what, exc):
    if os.environ.get("REQUIRE_SERVICES") == "1":
        raise exc
    pytest.skip(f"{what} injoignable ({exc}) : lancer `docker compose up -d`")


@pytest.fixture
def conn():
    try:
        connection = db.get_connection()
    except psycopg.OperationalError as exc:
        _unavailable("PostgreSQL", exc)
    db.init_schema(connection)
    connection.execute("TRUNCATE processed_files RESTART IDENTITY CASCADE")
    yield connection
    connection.close()
    # Base remise à vide : les tests ne laissent rien derrière eux
    # (connexion neuve, celle du test a pu être volontairement coupée)
    with db.get_connection() as clean:
        clean.execute("TRUNCATE processed_files RESTART IDENTITY CASCADE")


@pytest.fixture
def s3():
    """Client S3 + bucket neuf propre à chaque test (supprimé à la fin)."""
    client = s3_storage.get_client()
    bucket = f"test-{uuid.uuid4().hex[:12]}"
    try:
        s3_storage.ensure_bucket(client, bucket)
    except (BotoCoreError, ClientError) as exc:
        _unavailable("Service S3", exc)
    yield client, bucket
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])
    client.delete_bucket(Bucket=bucket)
