"""S3 I/O helpers para el paquete rag.

Solo operaciones de lectura/listado (el runtime RAG no escribe en data/).
"""

from __future__ import annotations

from boto3.session import Session
from botocore.config import Config

from . import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Session().client(
            "s3",
            endpoint_url=config.S3_ENDPOINT_URL,
            region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY_ID,
            aws_secret_access_key=config.S3_SECRET_ACCESS_KEY,
            aws_session_token=config.S3_SESSION_TOKEN,
            verify=config.S3_VERIFY_SSL,
            config=Config(s3={"addressing_style": config.S3_ADDRESSING_STYLE}),
        )
    return _client


def get_bucket() -> str:
    if not config.S3_BUCKET_NAME:
        raise RuntimeError("S3_BUCKET_NAME no está definida. Agrégala al archivo .env.")
    return config.S3_BUCKET_NAME


def get_client():
    return _get_client()


def list_keys(prefix: str, suffix: str = "") -> list[str]:
    """Lista todos los keys bajo *prefix* que terminen en *suffix*, ordenados."""
    paginator = _get_client().get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=get_bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not suffix or key.endswith(suffix):
                keys.append(key)
    return sorted(keys)


def read_text(key: str, encoding: str = "utf-8") -> str:
    """Descarga un objeto S3 y devuelve su contenido como string."""
    response = _get_client().get_object(Bucket=get_bucket(), Key=key)
    return response["Body"].read().decode(encoding)
