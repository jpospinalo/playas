# rag/core/retriever.py
"""Retriever híbrido BM25 + vectorial con fusión RRF.

Combina búsqueda léxica (BM25 sobre texto aumentado con keywords y resumen)
con búsqueda semántica (embeddings de Ollama vía ChromaDB) usando Weighted
Reciprocal Rank Fusion (RRF, c=160). Los sub-retrievers se ejecutan en
paralelo desde una única capa de concurrencia async (``asyncio.gather`` +
``asyncio.to_thread`` por sub-retriever, sin ningún ``ThreadPoolExecutor``
propio — T3.2) cuando se invoca vía ``ainvoke()``; ``invoke()`` (síncrono)
sigue disponible y produce el mismo resultado, ejecutando los sub-retrievers
secuencialmente.

Singletons de módulo (ChromaDB client, vectorstore, BM25 index) se pre-calientan
en el arranque de la app vía ``init_retrievers()`` y se reutilizan entre requests.

Componentes principales:
  - ``HybridEnsembleRetriever`` — retriever híbrido configurable (BM25 + vector).
  - ``_FilteredRetriever`` — wrapper que filtra por ``doc_type`` en memoria
    (usado para BM25, que no soporta filtros de metadata nativos).
  - ``OllamaReranker`` — reranker opcional basado en LLM (no usado en el flujo
    principal; disponible para experimentación).
  - ``balance_by_doc_type()`` — función pura para garantizar cuota mínima por
    tipo de documento en los top-k resultados.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import chromadb
import numpy as np
import requests
from langchain_chroma import Chroma
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from rag.config import CHROMA_COLLECTION as CHROMA_COLLECTION_NAME
from rag.config import (
    CHROMA_HOST,
    CHROMA_PORT,
    OLLAMA_RERANK_BASE_URL,
    OLLAMA_RERANK_MODEL,
)

from .embeddings import OllamaEmbeddings

# ---------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------
#
# T2.4: CHROMA_HOST/CHROMA_PORT/CHROMA_COLLECTION_NAME/OLLAMA_RERANK_*
# ahora vienen de rag.config (resolución centralizada de .env, T2.3) en vez
# de leerse aquí con un load_dotenv() + os.getenv() propios. Mismos nombres
# y misma precedencia de alias que antes — ver rag/config.py.

EMBEDDINGS = OllamaEmbeddings()

# ---------------------------------------------------------------------
# Singletons de módulo — reutilizados entre requests
# ---------------------------------------------------------------------

_chroma_client: Any | None = None
_chroma_vectorstore: Chroma | None = None
_bm25_base: BM25Retriever | None = None


def _tokenize_bm25(text: str) -> list[str]:
    """Replica el preprocesamiento histórico de BM25Retriever: ``str.split``."""
    return text.split()


class BM25Retriever(BaseRetriever):
    """Adaptador mínimo de ``rank_bm25`` compatible con el retriever anterior.

    ``vectorizer`` es ``None`` cuando el corpus está vacío: ``BM25Okapi([])``
    lanza ``ZeroDivisionError`` (divide por la longitud promedio de
    documento, indefinida con cero documentos), así que en ese caso no se
    construye ningún índice. ``_get_relevant_documents`` devuelve entonces
    una lista vacía —igual que un índice real sin coincidencias— en vez de
    fabricar evidencia.

    Con un vectorizador real, no se usa ``rank_bm25``'s ``get_top_n()``:
    internamente hace ``np.argsort(get_scores(query))[::-1][:n]`` sin filtrar
    nada, así que con un corpus más chico que ``k`` (o documentos sin ningún
    término en común con la consulta) completaba igual el top-k con
    documentos de score EXACTAMENTE 0 — evidencia fabricada, sin señal
    léxica real, que competía en la fusión RRF como si fuera un candidato
    genuino. Se reimplementa el mismo cálculo (``get_scores`` +
    ``np.argsort(scores)[::-1]``, idéntico al que ``get_top_n`` ya hacía
    internamente) descartando los índices con score == 0 antes de completar
    el top-k. El orden de desempate ante scores iguales se preserva
    deliberadamente igual a como lo produce ``np.argsort`` con quicksort (su
    ``kind`` por defecto, sin especificar — NO estable ante empates): es un
    detalle de implementación de NumPy, no una garantía documentada por
    ``np.argsort``, pero es exactamente el mismo comportamiento que ya tenía
    el índice histórico vía ``get_top_n``, así que no se introduce ningún
    cambio de desempate nuevo.
    """

    vectorizer: Any | None
    docs: list[Document] = Field(repr=False)
    k: int = 4

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        if self.vectorizer is None:
            return []

        assert self.vectorizer.corpus_size == len(self.docs), (
            "Los documentos no coinciden con el corpus indexado por BM25."
        )

        scores = self.vectorizer.get_scores(_tokenize_bm25(query))
        order = np.argsort(scores)[::-1]

        selected: list[Document] = []
        for idx in order:
            if len(selected) >= self.k:
                break
            if scores[idx] == 0:
                # Sin señal léxica real: no fabricar evidencia solo para
                # completar el top-k solicitado.
                continue
            selected.append(self.docs[idx])
        return selected


def _get_chroma_client() -> Any:
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

    Corpus vacío: no se invoca ``BM25Okapi([])`` (lanza ``ZeroDivisionError``)
    ni se fabrica un documento placeholder como evidencia falsa —lo que antes
    permitía que BM25 devolviera ese placeholder como si fuera un fragmento
    real del corpus—. En su lugar, el índice queda sin vectorizador: las
    búsquedas devuelven una lista vacía (ver ``BM25Retriever``), y el arranque
    de la app (``init_retrievers()``) no falla por tener la colección vacía.
    """
    global _bm25_base
    if _bm25_base is None:
        docs = load_all_docs_from_chroma()

        if not docs:
            _bm25_base = BM25Retriever(vectorizer=None, docs=[], k=50)
            return _bm25_base

        from rank_bm25 import BM25Okapi

        augmented_texts: list[str] = []
        for d in docs:
            meta = d.metadata or {}
            parts = [d.page_content]
            if kw := meta.get("keywords_str", ""):
                parts.append(kw)
            if sm := meta.get("summary", ""):
                parts.append(sm)
            augmented_texts.append(" ".join(parts))

        corpus = [_tokenize_bm25(t) for t in augmented_texts]
        vectorizer = BM25Okapi(corpus)
        # k=50 como techo máximo; se limita en get_bm25_retriever()
        _bm25_base = BM25Retriever(vectorizer=vectorizer, docs=docs, k=50)
    return _bm25_base


def bm25_index_is_empty() -> bool:
    """``True`` si el índice BM25 ya se construyó y el corpus está vacío.

    Distingue "aún no inicializado" (``_bm25_base is None`` → ``False``, ya
    que no hay nada que reportar como vacío todavía) de "inicializado pero
    sin evidencia" (``True``). Pensado como gancho interno para un futuro
    endpoint de readiness (T2.5): permite comprobar el estado del corpus sin
    volver a consultar Chroma en cada chequeo. No expone estado nuevo por sí
    sola —no hay ningún endpoint que la use todavía—.
    """
    return _bm25_base is not None and not _bm25_base.docs


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

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        docs = self.inner.invoke(query)
        allowed = set(self.doc_types)
        return [d for d in docs if (d.metadata or {}).get("doc_type") in allowed]


def _has_retrievable_content(text: str) -> bool:
    """Filtro conservador post-fusión: descarta candidatos puramente
    estructurales (sin ningún carácter alfanumérico — p. ej. chunks que solo
    contienen separadores, guiones o espacios), un problema conocido de un
    subconjunto de chunks del corpus. No filtra por longitud ni idioma, solo
    por la ausencia total de contenido alfanumérico, para evitar descartar
    fragmentos legítimos pero cortos (p. ej. "Prohíbese pescar.").
    """
    return any(c.isalnum() for c in text)


# ---------------------------------------------------------------------
# HybridEnsembleRetriever propio
# ---------------------------------------------------------------------


class HybridEnsembleRetriever(BaseRetriever):
    """
    Retriever híbrido que combina varios sub-retrievers usando
    Weighted Reciprocal Rank Fusion (RRF).

    Concurrencia (T3.2): una sola capa. ``ainvoke()`` (usado por el grafo en
    producción, ver ``agent.retrieve_forced_node``) despacha todos los
    sub-retrievers con ``asyncio.gather`` + ``asyncio.to_thread`` — cada
    sub-retriever corre en el executor por defecto de asyncio, sin crear
    ningún ``ThreadPoolExecutor`` propio anidado dentro de otra capa de
    concurrencia. ``invoke()`` (síncrono, para scripts/demo) ejecuta los
    mismos sub-retrievers de forma secuencial y produce exactamente el mismo
    resultado fusionado — la fusión RRF no depende del orden de ejecución,
    solo del orden de ``self.retrievers``.
    """

    retrievers: list[BaseRetriever]
    weights: list[float]
    c: int = 160  # constante RRF
    id_key: str | None = "chunk_id"
    max_results: int = 4

    def _fuse(self, all_results: list[list[Document]]) -> list[Document]:
        """Fusión RRF ponderada, común a las rutas síncrona y asíncrona."""
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

        # Se recorre en orden de score descendente y se descartan los
        # candidatos sin contenido alfanumérico (basura estructural del
        # corpus), rellenando con el siguiente mejor candidato en vez de
        # simplemente truncar a max_results. No afecta a BM25, al vector
        # store, a los pesos ni a k: opera solo sobre el resultado ya
        # fusionado, así que nunca devuelve más de max_results documentos.
        sorted_ids = sorted(scores, key=lambda identifier: scores[identifier], reverse=True)
        selected: list[Document] = []
        for doc_id in sorted_ids:
            if len(selected) >= self.max_results:
                break
            doc = doc_by_id[doc_id]
            if not _has_retrievable_content(doc.page_content or ""):
                continue
            selected.append(doc)
        return selected

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        all_results: list[list[Document]] = [r.invoke(query) for r in self.retrievers]
        return self._fuse(all_results)

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Any,
    ) -> list[Document]:
        del run_manager
        # Única capa de concurrencia: un asyncio.to_thread por sub-retriever,
        # despachados juntos con gather. Sin ThreadPoolExecutor propio.
        all_results: list[list[Document]] = await asyncio.gather(
            *(asyncio.to_thread(r.invoke, query) for r in self.retrievers)
        )
        return self._fuse(all_results)


def get_ensemble_retriever(
    k: int = 4,
    k_candidates: int | None = None,
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
    final_k = max(1, k)
    candidate_k = max(final_k, k_candidates or final_k)
    vector_retriever = get_vector_retriever(k=candidate_k, doc_types=doc_types)

    if doc_types:
        # BM25 filtra por metadata después de recuperar. Se amplía su conjunto
        # de candidatos para evitar quedarse corto tras descartar otros tipos.
        bm25_inner = get_bm25_retriever(k=min(candidate_k * 4, 50))
        bm25_retriever: BaseRetriever = _FilteredRetriever(inner=bm25_inner, doc_types=doc_types)
    else:
        bm25_retriever = get_bm25_retriever(k=candidate_k)

    return HybridEnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[bm25_weight, vector_weight],
        max_results=final_k,
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
        base_url: str | None = OLLAMA_RERANK_BASE_URL,
        model: str | None = OLLAMA_RERANK_MODEL,
        timeout: float = 60.0,
    ) -> None:
        if not base_url or not model:
            raise ValueError("OLLAMA_RERANK_BASE_URL y OLLAMA_RERANK_MODEL son obligatorios")
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
