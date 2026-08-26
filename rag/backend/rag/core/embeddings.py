# src/backend/embeddings.py

import os
from typing import cast

import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from langchain_core.embeddings import Embeddings as LCEmbeddings


class OllamaEmbeddingClient:
    """Shared HTTP client for Ollama embeddings.

    Ollama expone un embedding por petición (``"prompt": <un solo texto>``):
    no existe un endpoint de lote real. ``embed_one()`` es la operación
    unitaria genuina; ``embed()`` se conserva solo por compatibilidad y
    delega en ella para exactamente un texto.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL") or os.getenv(
            "OLLAMA_EMBED_BASE_URL", "http://localhost:11434"
        )
        self.model = os.getenv("OLLAMA_EMBEDDING_MODEL") or os.getenv(
            "OLLAMA_EMBED_MODEL", "embeddinggemma:latest"
        )
        # Sesión compartida: reutiliza la conexión HTTP entre llamadas sin
        # cambiar el vector devuelto, el modelo ni el proveedor.
        self._session = requests.Session()

    def embed_one(self, text: str) -> list[float]:
        """Calcula el embedding de un único texto.

        Valida la forma de la respuesta de Ollama: si ``embedding`` falta, no
        es una lista, está vacía o contiene algo que no sea un número, falla
        explícitamente en vez de propagar un ``KeyError`` o un vector con
        forma inesperada a quien llama.
        """
        try:
            response = self._session.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                "No fue posible conectar con Ollama para calcular embeddings. "
                f"Verifica que el servicio esté activo en {self.base_url} "
                f"y que el modelo '{self.model}' esté disponible."
            ) from exc
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Ollama devolvió una respuesta que no es JSON válido al calcular un embedding."
            ) from exc

        embedding = data.get("embedding") if isinstance(data, dict) else None
        if (
            not isinstance(embedding, list)
            or not embedding
            or not all(isinstance(value, int | float) for value in embedding)
        ):
            raise RuntimeError(
                "Ollama devolvió un embedding con forma inesperada (se esperaba una "
                f"lista no vacía de números): {embedding!r}"
            )
        return [float(value) for value in embedding]

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Compatibilidad retroactiva: acepta EXACTAMENTE un texto.

        No implementa un lote real —Ollama no lo ofrece— y por eso rechaza
        explícitamente cero o varios textos en vez de aceptarlos e ignorar
        todos menos el primero, como hacía la versión anterior.
        """
        if len(texts) != 1:
            raise ValueError(
                f"embed() acepta exactamente un texto (recibidos: {len(texts)}). "
                "Usa embed_one(texto) para un único texto, o invoca embed() "
                "una vez por texto."
            )
        return [self.embed_one(texts[0])]


class OllamaEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible embedding function backed by Ollama."""

    def __init__(self) -> None:
        self._client = OllamaEmbeddingClient()

    def __call__(self, input: Documents) -> Embeddings:
        return cast(Embeddings, [self._client.embed_one(text) for text in input])


class OllamaEmbeddings(LCEmbeddings):
    """LangChain-compatible embeddings backed by Ollama."""

    def __init__(self) -> None:
        self._client = OllamaEmbeddingClient()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._client.embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_one(text)
