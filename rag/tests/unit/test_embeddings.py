"""T1.2 — contrato unitario de embeddings: ``embed_one`` es la operación
real; ``embed`` se conserva solo por compatibilidad y rechaza cero o varios
textos en vez de aceptarlos e ignorar todos menos el primero."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from rag.core.embeddings import (
    OllamaEmbeddingClient,
    OllamaEmbeddingFunction,
    OllamaEmbeddings,
)


def _client_with_mocked_session(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[OllamaEmbeddingClient, MagicMock]:
    client = OllamaEmbeddingClient()
    mock_session = MagicMock()
    monkeypatch.setattr(client, "_session", mock_session)
    return client, mock_session


def _response(json_data: Any, status_ok: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    if status_ok:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# embed_one — un texto produce un vector
# ---------------------------------------------------------------------------


def test_embed_one_returns_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    client, mock_session = _client_with_mocked_session(monkeypatch)
    mock_session.post.return_value = _response({"embedding": [0.1, 0.2, 0.3]})

    result = client.embed_one("texto de prueba")

    assert result == [0.1, 0.2, 0.3]
    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args.kwargs
    assert call_kwargs["json"]["prompt"] == "texto de prueba"


def test_embed_one_reuses_the_same_http_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirma que las llamadas comparten la sesión (una sola conexión
    reutilizada), sin cambiar el vector devuelto ni el proveedor."""
    client, mock_session = _client_with_mocked_session(monkeypatch)
    mock_session.post.return_value = _response({"embedding": [1.0]})

    client.embed_one("a")
    client.embed_one("b")

    assert mock_session.post.call_count == 2
    assert client._session is mock_session  # misma sesión en ambas llamadas


# ---------------------------------------------------------------------------
# embed() — compatibilidad: exactamente un texto; cero o varios fallan
# ---------------------------------------------------------------------------


def test_embed_with_exactly_one_text_delegates_to_embed_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, mock_session = _client_with_mocked_session(monkeypatch)
    mock_session.post.return_value = _response({"embedding": [0.5, 0.6]})

    result = client.embed(["único texto"])

    assert result == [[0.5, 0.6]]


def test_embed_with_zero_texts_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client_with_mocked_session(monkeypatch)
    with pytest.raises(ValueError, match="exactamente un texto"):
        client.embed([])


def test_embed_with_several_texts_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client_with_mocked_session(monkeypatch)
    with pytest.raises(ValueError, match="exactamente un texto"):
        client.embed(["a", "b", "c"])


# ---------------------------------------------------------------------------
# Fallos: HTTP, JSON inválido, forma inesperada del vector
# ---------------------------------------------------------------------------


def test_embed_one_propagates_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    client, mock_session = _client_with_mocked_session(monkeypatch)
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 server error")
    mock_session.post.return_value = resp

    with pytest.raises(requests.exceptions.HTTPError):
        client.embed_one("texto")


def test_embed_one_connection_error_raises_clear_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests

    client, mock_session = _client_with_mocked_session(monkeypatch)
    mock_session.post.side_effect = requests.exceptions.ConnectionError("refused")

    with pytest.raises(RuntimeError, match="No fue posible conectar con Ollama"):
        client.embed_one("texto")


def test_embed_one_invalid_json_raises_clear_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, mock_session = _client_with_mocked_session(monkeypatch)
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("not json")
    mock_session.post.return_value = resp

    with pytest.raises(RuntimeError, match="JSON válido"):
        client.embed_one("texto")


@pytest.mark.parametrize(
    "payload",
    [
        {},  # sin la clave "embedding"
        {"embedding": None},
        {"embedding": "no-es-una-lista"},
        {"embedding": []},  # lista vacía
        {"embedding": [0.1, "no-es-numero", 0.3]},
    ],
)
def test_embed_one_unexpected_shape_raises_clear_runtime_error(
    monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    client, mock_session = _client_with_mocked_session(monkeypatch)
    mock_session.post.return_value = _response(payload)

    with pytest.raises(RuntimeError, match="forma inesperada"):
        client.embed_one("texto")


# ---------------------------------------------------------------------------
# Los adaptadores existentes usan la operación unitaria, no el lote
# ---------------------------------------------------------------------------


def test_chroma_embedding_function_uses_embed_one_per_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fn = OllamaEmbeddingFunction()
    calls: list[str] = []

    def fake_embed_one(text: str) -> list[float]:
        calls.append(text)
        return [float(len(text))]

    monkeypatch.setattr(fn._client, "embed_one", fake_embed_one)
    monkeypatch.setattr(
        fn._client,
        "embed",
        lambda texts: (_ for _ in ()).throw(AssertionError("no debe usar embed() en lote")),
    )

    result = fn(["uno", "dos", "tres"])

    assert calls == ["uno", "dos", "tres"]
    assert result == [[3.0], [3.0], [4.0]]


def test_langchain_embeddings_embed_documents_uses_embed_one_per_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emb = OllamaEmbeddings()
    calls: list[str] = []
    monkeypatch.setattr(emb._client, "embed_one", lambda text: calls.append(text) or [1.0, 2.0])

    result = emb.embed_documents(["x", "y"])

    assert calls == ["x", "y"]
    assert result == [[1.0, 2.0], [1.0, 2.0]]


def test_langchain_embeddings_embed_query_uses_embed_one(monkeypatch: pytest.MonkeyPatch) -> None:
    emb = OllamaEmbeddings()
    calls: list[str] = []
    monkeypatch.setattr(emb._client, "embed_one", lambda text: calls.append(text) or [9.0])

    result = emb.embed_query("consulta")

    assert calls == ["consulta"]
    assert result == [9.0]
