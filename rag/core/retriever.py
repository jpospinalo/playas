# rag/core/retriever.py

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
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
# Configuración
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
# Singletons de módulo — reutilizados entre requests
# ---------------------------------------------------------------------

_chroma_client: chromadb.HttpClient | None = None
_chroma_vectorstore: Chroma | None = None
_bm25_base: BM25Retriever | None = None


def _get_chroma_client() -> chromadb.HttpClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return _chroma_client


def _get_chroma_vectorstore() -> Chroma:
    global _chroma_vectorstore
    if _chroma_vectorstore is None:
        _chroma_vectorstore = Chroma(
            client=_get_chroma_client(),
            collection_name=CHROMA_COLLECTION_NAME,
            embedding_function=EMBEDDINGS,
        )
    return _chroma_vectorstore


def _get_bm25_base() -> BM25Retriever:
    """
    Construye el índice BM25 una sola vez y lo reutiliza entre requests.

    El corpus se indexa con texto aumentado (page_content + keywords_str + summary)
    para mejorar el recall con terminología jurídica curada por Gemini, pero los
    documentos devueltos conservan el page_content original sin modificaciones.
    """
    global _bm25_base
    if _bm25_base is None:
        from langchain_community.retrievers.bm25 import default_preprocessing_func
        from rank_bm25 import BM25Okapi

        docs = load_all_docs_from_chroma()

        augmented_texts: list[str] = []
        for d in docs:
            meta = d.metadata or {}
            parts = [d.page_content]
            if kw := meta.get("keywords_str", ""):
                parts.append(kw)
            if sm := meta.get("summary", ""):
                parts.append(sm)
            augmented_texts.append(" ".join(parts))

        corpus = [default_preprocessing_func(t) for t in augmented_texts]
        vectorizer = BM25Okapi(corpus)
        # k=50 como techo máximo; se limita en get_bm25_retriever()
        _bm25_base = BM25Retriever(vectorizer=vectorizer, docs=docs, k=50)
    return _bm25_base


def init_retrievers() -> None:
    """
    Pre-calienta todos los singletons del retriever.
    Debe llamarse en el evento de arranque de la aplicación (lifespan).
    """
    _get_chroma_client()
    _get_chroma_vectorstore()
    _get_bm25_base()


# ---------------------------------------------------------------------
# Utilidades: cargar docs de Chroma
# ---------------------------------------------------------------------


def load_all_docs_from_chroma() -> list[Document]:
    """
    Lee todos los documentos de la colección en Chroma usando el cliente
    singleton (evita abrir nuevas conexiones en cada llamada).
    """
    collection = _get_chroma_client().get_collection(name=CHROMA_COLLECTION_NAME)
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
# Constructores de retrievers
# ---------------------------------------------------------------------


def _build_doc_type_filter(doc_types: list[str]) -> dict[str, Any]:
    """
    Construye el filtro de metadata de Chroma (clave ``filter`` en langchain_chroma)
    a partir de una lista de doc_types.

    - Un solo valor → ``{"doc_type": valor}``
    - Varios valores → ``{"doc_type": {"$in": [...]}}``
    """
    if len(doc_types) == 1:
        return {"doc_type": doc_types[0]}
    return {"doc_type": {"$in": list(doc_types)}}


def get_vector_retriever(k: int = 3, doc_types: list[str] | None = None):
    """
    Retriever semántico (denso) usando el vectorstore Chroma singleton.

    Si ``doc_types`` viene dado (p.ej. ["jurisprudencia"] o
    ["jurisprudencia", "normativa"]), se aplica un filtro de metadata nativo de
    Chroma sobre el campo ``doc_type``. Si es None, no se añade filtro y el
    comportamiento es idéntico al original.
    """
    search_kwargs: dict[str, Any] = {"k": k}
    if doc_types:
        search_kwargs["filter"] = _build_doc_type_filter(doc_types)
    return _get_chroma_vectorstore().as_retriever(search_kwargs=search_kwargs)


def get_bm25_retriever(k: int = 3) -> BM25Retriever:
    """
    Retriever BM25 léxico respaldado por el índice pre-construido y cacheado.
    Devuelve una copia ligera (sin recrear el índice) con el k solicitado.
    """
    return _get_bm25_base().model_copy(update={"k": k})


class _FilteredRetriever(BaseRetriever):
    """
    Envuelve otro retriever y filtra sus resultados por ``doc_type``.

    BM25 no soporta filtros de metadata nativos, así que este wrapper invoca al
    retriever interno (que normalmente pide más candidatos de los necesarios) y
    descarta los Documents cuyo ``metadata.get("doc_type")`` no esté en
    ``doc_types``.
    """

    inner: BaseRetriever
    doc_types: list[str]

    def _get_relevant_documents(self, query: str) -> list[Document]:
        docs = self.inner.invoke(query)
        allowed = set(self.doc_types)
        return [d for d in docs if (d.metadata or {}).get("doc_type") in allowed]


# ---------------------------------------------------------------------
# HybridEnsembleRetriever propio
# ---------------------------------------------------------------------


class HybridEnsembleRetriever(BaseRetriever):
    """
    Retriever híbrido que combina varios sub-retrievers usando
    Weighted Reciprocal Rank Fusion (RRF).

    Los sub-retrievers se invocan en paralelo mediante un ThreadPoolExecutor,
    reduciendo la latencia porque BM25 (CPU) y la búsqueda vectorial (IO/HTTP)
    pueden ejecutarse concurrentemente.
    """

    retrievers: list[BaseRetriever]
    weights: list[float]
    c: int = 160  # constante RRF
    id_key: str | None = "chunk_id"

    def _get_relevant_documents(self, query: str) -> list[Document]:
        # Invocar todos los sub-retrievers en paralelo
        with ThreadPoolExecutor(max_workers=len(self.retrievers)) as pool:
            futures = [pool.submit(r.invoke, query) for r in self.retrievers]
            all_results: list[list[Document]] = [f.result() for f in futures]

        # Fusión de rankings con RRF ponderado
        scores: dict[str, float] = {}
        doc_by_id: dict[str, Document] = {}

        for docs, w in zip(all_results, self.weights, strict=False):
            for rank, doc in enumerate(docs, start=1):
                if self.id_key and self.id_key in (doc.metadata or {}):
                    doc_id = str(doc.metadata[self.id_key])
                else:
                    doc_id = doc.page_content

                doc_by_id.setdefault(doc_id, doc)
                scores[doc_id] = scores.get(doc_id, 0.0) + w / (rank + self.c)

        sorted_ids = sorted(scores, key=scores.get, reverse=True)
        return [doc_by_id[i] for i in sorted_ids]


def get_ensemble_retriever(
    k: int = 3,
    bm25_weight: float = 0.3,
    vector_weight: float = 0.7,
    doc_types: list[str] | None = None,
) -> HybridEnsembleRetriever:
    """
    Construye el retriever híbrido BM25 + vectorial usando componentes cacheados.

    Si ``doc_types`` viene dado, se propaga a ambos sub-retrievers:
    - vector → filtro de metadata nativo de Chroma
    - BM25 → ``_FilteredRetriever`` (filtrado en memoria); se piden k*4 candidatos
      al BM25 antes de filtrar para no quedarse corto tras descartar tipos.

    La firma es retrocompatible: con ``doc_types=None`` el comportamiento es
    idéntico al original (ambos tipos, sin filtro).
    """
    vector_retriever = get_vector_retriever(k=k, doc_types=doc_types)

    if doc_types:
        bm25_inner = get_bm25_retriever(k=k * 4)
        bm25_retriever: BaseRetriever = _FilteredRetriever(inner=bm25_inner, doc_types=doc_types)
    else:
        bm25_retriever = get_bm25_retriever(k=k)

    return HybridEnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[bm25_weight, vector_weight],
    )


def balance_by_doc_type(
    docs: list[Document],
    k: int,
    min_per_type: dict[str, int] | None = None,
) -> list[Document]:
    """
    Devuelve los top-k documentos de una lista ya ordenada por relevancia,
    garantizando una cuota mínima por ``doc_type``.

    Para cada tipo ``t`` en ``min_per_type``, asegura que el resultado incluya al
    menos ``min_per_type[t]`` documentos de ese tipo (si existen en ``docs``),
    tomando los mejor rankeados de cada tipo para cubrir la cuota y completando
    el resto con los documentos restantes en su orden original de relevancia.

    Si ``min_per_type`` es None, devuelve ``docs[:k]`` sin cambios.

    Función pura y testeable, pensada para que el caller la use tras la fusión
    (p.ej. en el agente/generador) y evite que la normativa quede tapada por la
    jurisprudencia cuando ambos tipos compiten por los primeros puestos. No está
    conectada de forma obligatoria al flujo de retrieval.
    """
    if min_per_type is None:
        return docs[:k]

    selected: list[Document] = []
    selected_ids: set[int] = set()

    def _doc_type(doc: Document) -> Any:
        return (doc.metadata or {}).get("doc_type")

    # 1) Cubrir la cuota mínima por tipo con los mejor rankeados de cada uno.
    for dtype, quota in min_per_type.items():
        if quota <= 0:
            continue
        taken = 0
        for idx, doc in enumerate(docs):
            if taken >= quota or len(selected) >= k:
                break
            if idx in selected_ids:
                continue
            if _doc_type(doc) == dtype:
                selected.append(doc)
                selected_ids.add(idx)
                taken += 1

    # 2) Completar hasta k con el resto, respetando el orden de relevancia.
    for idx, doc in enumerate(docs):
        if len(selected) >= k:
            break
        if idx in selected_ids:
            continue
        selected.append(doc)
        selected_ids.add(idx)

    return selected[:k]


# ---------------------------------------------------------------------
# Reranker con modelo de Ollama (opcional, no usado en el flujo principal)
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
    base_retriever = get_ensemble_retriever(k=5)
    candidates = base_retriever.invoke(query)

    if use_reranker:
        reranker = OllamaReranker()
        docs = reranker.rerank(query, candidates, top_k=k)
    else:
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
    demo(query="¿cómo se llamaba el gato del cuento?")
