"""Pruebas TDD para la configuración S3-compatible del backend RAG."""

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


def reload_rag_config(monkeypatch: pytest.MonkeyPatch, **env: str | None):
    for var in S3_ENV_VARS:
        monkeypatch.setenv(var, "")
    for key, value in env.items():
        if value is None:
            monkeypatch.setenv(key, "")
        else:
            monkeypatch.setenv(key, value)

    import rag.config as config_module

    return importlib.reload(config_module)


def reload_rag_s3_client():
    import rag.s3_client as s3_client_module

    return importlib.reload(s3_client_module)


def test_rag_s3_config_defaults(monkeypatch: pytest.MonkeyPatch):
    config = reload_rag_config(monkeypatch, S3_BUCKET_NAME="playas-bucket")

    assert config.S3_BUCKET_NAME == "playas-bucket"
    assert config.S3_ENDPOINT_URL is None
    assert config.S3_REGION == "us-east-1"
    assert config.S3_ACCESS_KEY_ID is None
    assert config.S3_SECRET_ACCESS_KEY is None
    assert config.S3_SESSION_TOKEN is None
    assert config.S3_ADDRESSING_STYLE == "auto"
    assert config.S3_VERIFY_SSL is True


def test_rag_s3_config_parses_explicit_provider_values(monkeypatch: pytest.MonkeyPatch):
    config = reload_rag_config(
        monkeypatch,
        S3_BUCKET_NAME="playas-local",
        S3_ENDPOINT_URL="https://objects.railway.internal",
        S3_REGION="us-east-1",
        S3_ACCESS_KEY_ID="railway",
        S3_SECRET_ACCESS_KEY="railway-secret",
        S3_SESSION_TOKEN="railway-token",
        S3_ADDRESSING_STYLE="virtual",
        S3_VERIFY_SSL="/tmp/custom-ca.pem",
    )

    assert config.S3_ENDPOINT_URL == "https://objects.railway.internal"
    assert config.S3_REGION == "us-east-1"
    assert config.S3_ACCESS_KEY_ID == "railway"
    assert config.S3_SECRET_ACCESS_KEY == "railway-secret"
    assert config.S3_SESSION_TOKEN == "railway-token"
    assert config.S3_ADDRESSING_STYLE == "virtual"
    assert config.S3_VERIFY_SSL == "/tmp/custom-ca.pem"


def test_rag_s3_client_uses_explicit_session_configuration(monkeypatch: pytest.MonkeyPatch):
    reload_rag_config(
        monkeypatch,
        S3_BUCKET_NAME="playas-local",
        S3_ENDPOINT_URL="https://objects.railway.internal",
        S3_REGION="us-east-1",
        S3_ACCESS_KEY_ID="railway",
        S3_SECRET_ACCESS_KEY="railway-secret",
        S3_SESSION_TOKEN="railway-token",
        S3_ADDRESSING_STYLE="virtual",
        S3_VERIFY_SSL="/tmp/custom-ca.pem",
    )
    s3_client = reload_rag_s3_client()

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
    assert config_calls[0] == {"s3": {"addressing_style": "virtual"}}
    assert len(client_calls) == 1
    service_name, kwargs = client_calls[0]
    assert service_name == "s3"
    assert kwargs["endpoint_url"] == "https://objects.railway.internal"
    assert kwargs["region_name"] == "us-east-1"
    assert kwargs["aws_access_key_id"] == "railway"
    assert kwargs["aws_secret_access_key"] == "railway-secret"
    assert kwargs["aws_session_token"] == "railway-token"
    assert kwargs["verify"] == "/tmp/custom-ca.pem"
    assert kwargs["config"] == {"wrapped": {"s3": {"addressing_style": "virtual"}}}


def test_rag_get_bucket_fails_fast_without_bucket(monkeypatch: pytest.MonkeyPatch):
    reload_rag_config(monkeypatch, S3_BUCKET_NAME="")
    s3_client = reload_rag_s3_client()

    with pytest.raises(RuntimeError, match="S3_BUCKET_NAME"):
        s3_client.get_bucket()
