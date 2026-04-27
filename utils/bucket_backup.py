"""
Descarga todos los objetos del bucket S3 (S3_BUCKET_NAME desde .env)
a una carpeta local bucket-backup-<YYYYMMDD-HHMMSS>/ en la raíz del proyecto.

Uso:
    uv run python -m utils.bucket_backup
    make bucket-backup
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    bucket_name = os.getenv("S3_BUCKET_NAME", "").strip()
    if not bucket_name:
        print("Error: S3_BUCKET_NAME no está definido en el .env", file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = PROJECT_ROOT / f"bucket-backup-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"Bucket:  {bucket_name}")
    print(f"Destino: {backup_dir}")

    try:
        s3 = boto3.client("s3")
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name)

        total = 0
        for page in pages:
            for obj in page.get("Contents", []):
                key: str = obj["Key"]
                dest = backup_dir / key
                dest.parent.mkdir(parents=True, exist_ok=True)
                print(f"  ↓ {key}")
                s3.download_file(bucket_name, key, str(dest))
                total += 1

    except (BotoCoreError, ClientError) as exc:
        print(f"Error al conectar con S3: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✓ {total} objeto(s) descargado(s) en {backup_dir}")


if __name__ == "__main__":
    main()
