# src/backend/retriever.py

from __future__ import annotations

import os
import re
from typing import Any

import chromadb
import requests
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from .embeddings import OllamaEmbeddings

# ---------------------------------------------------------------------
# Constantes (ajusta si cambian)
# ---------------------------------------------------------------------

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME")

# Máquina de RERANKING (Ollama con llama3.2:3b)
OLLAMA_RERANK_BASE_URL = os.getenv("OLLAMA_RERANK_BASE_URL")
OLLAMA_RERANK_MODEL = os.getenv("OLLAMA_RERANK_MODEL")

EMBEDDINGS = OllamaEmbeddings()


# ---------------------------------------------------------------------
# Utilidades: cargar docs de Chroma
# ---------------------------------------------------------------------


def load_all_docs_from_chroma() -> list[Document]:
    """
    Lee todos los documentos de la colección en Chroma y los devuelve
    como objetos LangChain Document.
    """
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_collection(name=CHROMA_COLLECTION_NAME)

    raw = collection.get(include=["documents", "metadatas"])

    docs: list[Document] = []
    ids = raw.get("ids", [])

    for text, meta, _id in zip(
        raw.get("documents", []),
        raw.get("metadatas", []),
        ids,
        strict=False,
    ):
        if not text:
            continue
        metadata: dict[str, Any] = meta or {}
        metadata.setdefault("id", _id)
        docs.append(Document(page_content=text, metadata=metadata))

    return docs


# ---------------------------------------------------------------------
# Constructores de retrievers simples
# ---------------------------------------------------------------------


def get_vector_retriever(k: int = 3):
    """
    Retriever semántico (denso) usando Chroma + embeddings de Ollama.
    """
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

    vectorstore = Chroma(
        client=client,
        collection_name=CHROMA_COLLECTION_NAME,
        embedding_function=EMBEDDINGS,
    )

    return vectorstore.as_retriever(search_kwargs={"k": k})


def get_bm25_retriever(k: int = 3):
    """
    Retriever léxico BM25 basado en los mismos documentos que están en Chroma.
    Carga todos los documentos en memoria (suficiente para la demo).
    """
    docs = load_all_docs_from_chroma()
    bm25 = BM25Retriever.from_documents(docs)
    bm25.k = k
    return bm25


# ---------------------------------------------------------------------
# HybridEnsembleRetriever propio
# ---------------------------------------------------------------------


class HybridEnsembleRetriever(BaseRetriever):
    """
    Retriever híbrido que combina varios retrievers usando
    Weighted Reciprocal Rank Fusion (RRF).
    """

    retrievers: list[BaseRetriever]
    weights: list[float]
    c: int = 160  # constante RRF
    id_key: str | None = "chunk_id"

    def _get_relevant_documents(self, query: str) -> list[Document]:
        # 1) Obtener resultados de cada retriever
        all_results: list[list[Document]] = [r.invoke(query) for r in self.retrievers]

        # 2) Fusión de rankings con RRF ponderado
        scores: dict[str, float] = {}
        doc_by_id: dict[str, Document] = {}

        for docs, w in zip(all_results, self.weights, strict=False):
            for rank, doc in enumerate(docs, start=1):
                # Identificador estable para el doc
                if self.id_key and self.id_key in (doc.metadata or {}):
                    doc_id = str(doc.metadata[self.id_key])
                else:
                    # Fallback: usar el contenido completo
                    doc_id = doc.page_content

                doc_by_id.setdefault(doc_id, doc)
                scores[doc_id] = scores.get(doc_id, 0.0) + w / (rank + self.c)

        # 3) Ordenar por score descendente
        sorted_ids = sorted(scores, key=scores.get, reverse=True)
        return [doc_by_id[i] for i in sorted_ids]


def get_ensemble_retriever(
    k: int = 3,
    bm25_weight: float = 0.3,
    vector_weight: float = 0.7,
) -> HybridEnsembleRetriever:
    """
    Construye el retriever híbrido BM25 + vectorial.
    """
    bm25_retriever = get_bm25_retriever(k=k)
    vector_retriever = get_vector_retriever(k=k)

    return HybridEnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[bm25_weight, vector_weight],
    )


# ---------------------------------------------------------------------
# Reranker con modelo de Ollama
# ---------------------------------------------------------------------


class OllamaReranker:
    """
    Reranker basado en LLM de Ollama.
    Para cada (query, doc) devuelve un score 0–10 y reordena.
    """

    def __init__(
        self,
        base_url: str = OLLAMA_RERANK_BASE_URL,
        model: str = OLLAMA_RERANK_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _score_one(self, query: str, doc: Document) -> float:
        # Truncar contenido para no enviar textos gigantes
        content = doc.page_content
        if len(content) > 1500:
            content = content[:1500]

        prompt = f"""
Eres un sistema que evalúa la relevancia de un fragmento de texto frente a una pregunta.

Pregunta:
{query}

Fragmento:
\"\"\"{content}\"\"\"

Asigna un puntaje de relevancia entre 0 y 10, donde:
- 0 = totalmente irrelevante
- 10 = extremadamente relevante

Responde SOLO con un número (puede tener decimales), sin texto adicional.
"""

        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": 1024,
                    "num_predict": 16,
                },
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()

        m = re.search(r"(\d+(\.\d+)?)", text)
        if not m:
            return 0.0

        score = float(m.group(1))
        if score < 0:
            score = 0.0
        if score > 10:
            score = 10.0
        return score

    def rerank(self, query: str, docs: list[Document], top_k: int = 3) -> list[Document]:
        scored: list[tuple[float, Document]] = []
        for d in docs:
            s = self._score_one(query, d)
            scored.append((s, d))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for s, d in scored[:top_k]]


# ---------------------------------------------------------------------
# Ejemplo de uso desde terminal
# ---------------------------------------------------------------------


def demo(
    query: str = "¿cómo se llamaba el gato del cuento?",
    k: int = 4,
    use_reranker: bool = False,
) -> None:
    """
    Demostración rápida de uso del retriever híbrido y el reranker.
    """
    # 1) Retrieve híbrido con más candidatos
    base_retriever = get_ensemble_retriever(k=5)
    candidates = base_retriever.invoke(query)

    # 2) Opcional: Reranking con LLM de Ollama
    if use_reranker:
        reranker = OllamaReranker()
        docs = reranker.rerank(query, candidates, top_k=k)
    else:
        # Sin reranker, solo usamos los primeros k candidatos del ensemble
        docs = candidates[:k]

    print(f"\nConsulta: {query}\n")
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        src = meta.get("source", "desconocido")
        chunk_id = meta.get("chunk_id", meta.get("id", "sin_id"))
        print(f"[{i}] source={src} | chunk_id={chunk_id}")
        print(d.page_content.replace("\n", " "))
        print("-" * 80)


if __name__ == "__main__":
    # Con reranker
    demo(query="¿cómo se llamaba el gato del cuento?")

    # Sin reranker
    # demo(use_reranker=False)
