"""Pruebas TDD para las plantillas locales de object storage."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ingest_compose_declares_minio_and_bootstrap():
    content = (REPO_ROOT / "docker-compose.ingest.yml").read_text(encoding="utf-8")

    assert "minio:" in content
    assert "minio-bootstrap:" in content
    assert "S3_ENDPOINT_URL: http://minio:9000" in content
    assert "S3_ADDRESSING_STYLE: path" in content
    assert "rag-playas-minio-data" in content


def test_rag_compose_declares_minio_and_bootstrap():
    content = (REPO_ROOT / "docker-compose.rag.yml").read_text(encoding="utf-8")

    assert "minio:" in content
    assert "minio-bootstrap:" in content
    assert "S3_ENDPOINT_URL: http://minio:9000" in content
    assert "S3_ADDRESSING_STYLE: path" in content
    assert "rag-playas-minio-data" in content


def test_env_example_lists_s3_compatible_contract():
    content = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "S3_BUCKET_NAME=" in content
    assert "S3_ENDPOINT_URL=" in content
    assert "S3_REGION=" in content
    assert "S3_ACCESS_KEY_ID=" in content
    assert "S3_SECRET_ACCESS_KEY=" in content
    assert "S3_SESSION_TOKEN=" in content
    assert "S3_ADDRESSING_STYLE=" in content
    assert "S3_VERIFY_SSL=" in content


def test_readme_documents_local_minio_and_s3_compatible_storage():
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "MinIO" in content
    assert "S3-compatible" in content
    assert "S3_ENDPOINT_URL" in content
