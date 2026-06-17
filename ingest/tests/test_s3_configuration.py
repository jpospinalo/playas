"""Pruebas TDD para la configuración S3-compatible de ingest."""

from __future__ import annotations

import importlib

import pytest

S3_ENV_VARS = (
    "S3_BUCKET_NAME",
    "S3_ENDPOINT_URL",
    "S3_REGION",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_SESSION_TOKEN",
    "S3_ADDRESSING_STYLE",
    "S3_VERIFY_SSL",
)


def reload_ingest_config(monkeypatch: pytest.MonkeyPatch, **env: str | None):
    for var in S3_ENV_VARS:
        monkeypatch.setenv(var, "")
    for key, value in env.items():
        if value is None:
            monkeypatch.setenv(key, "")
        else:
            monkeypatch.setenv(key, value)

    import ingest.config as config_module

    return importlib.reload(config_module)


def reload_ingest_s3_client():
    import ingest.s3_client as s3_client_module

    return importlib.reload(s3_client_module)


def test_ingest_s3_config_defaults(monkeypatch: pytest.MonkeyPatch):
    config = reload_ingest_config(monkeypatch, S3_BUCKET_NAME="playas-bucket")

    assert config.S3_BUCKET_NAME == "playas-bucket"
    assert config.S3_ENDPOINT_URL is None
    assert config.S3_REGION == "us-east-1"
    assert config.S3_ACCESS_KEY_ID is None
    assert config.S3_SECRET_ACCESS_KEY is None
    assert config.S3_SESSION_TOKEN is None
    assert config.S3_ADDRESSING_STYLE == "auto"
    assert config.S3_VERIFY_SSL is True


def test_ingest_s3_config_parses_explicit_provider_values(monkeypatch: pytest.MonkeyPatch):
    config = reload_ingest_config(
        monkeypatch,
        S3_BUCKET_NAME="playas-local",
        S3_ENDPOINT_URL="http://minio:9000",
        S3_REGION="us-east-2",
        S3_ACCESS_KEY_ID="minio",
        S3_SECRET_ACCESS_KEY="minio-secret",
        S3_SESSION_TOKEN="session-token",
        S3_ADDRESSING_STYLE="path",
        S3_VERIFY_SSL="false",
    )

    assert config.S3_ENDPOINT_URL == "http://minio:9000"
    assert config.S3_REGION == "us-east-2"
    assert config.S3_ACCESS_KEY_ID == "minio"
    assert config.S3_SECRET_ACCESS_KEY == "minio-secret"
    assert config.S3_SESSION_TOKEN == "session-token"
    assert config.S3_ADDRESSING_STYLE == "path"
    assert config.S3_VERIFY_SSL is False


def test_ingest_s3_client_uses_explicit_session_configuration(monkeypatch: pytest.MonkeyPatch):
    reload_ingest_config(
        monkeypatch,
        S3_BUCKET_NAME="playas-local",
        S3_ENDPOINT_URL="http://minio:9000",
        S3_REGION="us-east-2",
        S3_ACCESS_KEY_ID="minio",
        S3_SECRET_ACCESS_KEY="minio-secret",
        S3_SESSION_TOKEN="session-token",
        S3_ADDRESSING_STYLE="path",
        S3_VERIFY_SSL="false",
    )
    s3_client = reload_ingest_s3_client()

    config_calls: list[dict] = []
    client_calls: list[tuple[str, dict]] = []
    fake_client = object()

    def fake_config(**kwargs):
        config_calls.append(kwargs)
        return {"wrapped": kwargs}

    class FakeSession:
        def client(self, service_name: str, **kwargs):
            client_calls.append((service_name, kwargs))
            return fake_client

    monkeypatch.setattr(s3_client, "Config", fake_config, raising=False)
    monkeypatch.setattr(s3_client, "Session", FakeSession, raising=False)
    s3_client._client = None

    assert s3_client._get_client() is fake_client
    assert s3_client._get_client() is fake_client
    assert len(config_calls) == 1
    assert config_calls[0] == {"s3": {"addressing_style": "path"}}
    assert len(client_calls) == 1
    service_name, kwargs = client_calls[0]
    assert service_name == "s3"
    assert kwargs["endpoint_url"] == "http://minio:9000"
    assert kwargs["region_name"] == "us-east-2"
    assert kwargs["aws_access_key_id"] == "minio"
    assert kwargs["aws_secret_access_key"] == "minio-secret"
    assert kwargs["aws_session_token"] == "session-token"
    assert kwargs["verify"] is False
    assert kwargs["config"] == {"wrapped": {"s3": {"addressing_style": "path"}}}


def test_ingest_get_bucket_fails_fast_without_bucket(monkeypatch: pytest.MonkeyPatch):
    reload_ingest_config(monkeypatch, S3_BUCKET_NAME="")
    s3_client = reload_ingest_s3_client()

    with pytest.raises(RuntimeError, match="S3_BUCKET_NAME"):
        s3_client.get_bucket()
