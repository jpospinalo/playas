# rag/core/retriever.py
"""Retriever híbrido BM25 + vectorial con fusión RRF.

Combina búsqueda léxica (BM25 sobre texto aumentado con keywords y resumen)
con búsqueda semántica (embeddings de Ollama vía ChromaDB) usando Weighted
Reciprocal Rank Fusion (RRF, c=2). Los sub-retrievers se ejecutan en
paralelo desde una única capa de concurrencia async (``asyncio.gather`` +
``asyncio.to_thread`` por sub-retriever, sin ningún ``ThreadPoolExecutor``
propio) cuando se invoca vía ``ainvoke()``; ``invoke()`` (síncrono)
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

``balance_by_doc_type()`` no forma parte de la API de este módulo. Su ausencia
se protege mediante ``tests/unit/test_retriever_no_dead_code.py``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Any

import chromadb
import numpy as np
import requests
from langchain_chroma import Chroma
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field, model_validator

from rag.config import CHROMA_COLLECTION as CHROMA_COLLECTION_NAME
from rag.config import (
    CHROMA_HOST,
    CHROMA_PORT,
    OLLAMA_RERANK_BASE_URL,
    OLLAMA_RERANK_MODEL,
)

from .embeddings import OllamaEmbeddings
from .territorio import lugar_de_norma, lugares_mencionados, plano
from .territorio import priorizar_territorio as _priorizar_territorio

# ---------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------
#
# CHROMA_HOST/CHROMA_PORT/CHROMA_COLLECTION_NAME/OLLAMA_RERANK_* vienen de
# rag.config (resolución centralizada de .env) en vez de leerse aquí con un
# load_dotenv() + os.getenv() propios. Mismos nombres y misma precedencia
# de alias — ver rag/config.py.

EMBEDDINGS = OllamaEmbeddings()

# Constantes de fusión.
#
# Salen de la medición offline sobre el ground truth v0.2 del propio repo
# (validación holdout de 200 particiones: 183 mejoran, 4 empeoran), no de una
# elección arbitraria. Con c=160 cualquier candidato vectorial superaba a
# cualquier candidato léxico y la lista final era siempre el top-4 vectorial;
# c=2, BM25 0.6 y vector 0.4 recuperan el comportamiento híbrido y suben el
# acierto de documento en top-4 de 0.586 a 0.690 sin degradar el MRR.
#
# Con el tokenizador español (ver ``_tokenize_bm25``) la señal léxica es mucho
# más limpia y BM25 pasa a llevar la mayor parte del peso: 0.8/0.2 frente a
# 0.6/0.4. La elección se validó con 200 particiones aleatorias por mitades
# (ganancia en la mitad reservada de +0.022 en hit@4; 112 particiones mejor,
# 30 peor). ``RRF_C`` se mantiene en 2.
RRF_C = 2
BM25_WEIGHT = 0.8
VECTOR_WEIGHT = 0.2

# Puestos del top-k reservados a normas aplicables (si hay candidatas). Medido
# sobre el ground truth v0.2 (k=4): con 0 cupos solo se reordena y el acierto
# no cambia (0.724); con 1 sube a 0.741 y normativa 7→8/18, sin bajar
# jurisprudencia (0.875); 2 cupos no añaden nada, así que se queda en 1.
CUPOS_NORMATIVA = 1

# Palabras vacías del español que no aportan señal léxica al BM25.
_STOPWORDS_ES: frozenset[str] = frozenset(
    """
a al algo algun alguna algunas alguno algunos ante antes aqui asi aun cada como con
contra cual cuales cuando de del desde donde dos e el ella ellas ello ellos en entre
era eran es esa esas ese eso esos esta estaba estado estan estar estas este esto
estos fue fueron ha habia han hasta hay la las le les lo los mas me mi mis mucho muy
nada ni no nos nosotros o otra otras otro otros para pero poco por porque que quien
se sea segun ser si sido siempre sin sobre solo son su sus tambien tan tanto te
tiene tienen todo todos tu tus un una unas uno unos y ya yo
""".split()
)

# ---------------------------------------------------------------------
# Singletons de módulo — reutilizados entre requests
# ---------------------------------------------------------------------

_chroma_client: Any | None = None
_chroma_vectorstore: Chroma | None = None
_bm25_base: BM25Retriever | None = None


def _tokenize_bm25(text: str) -> list[str]:
    """Tokenizador léxico español para el índice BM25 y para las consultas.

    ``str.split()`` separaba solo por espacios, así que "Playa," y "playa", o
    "DIMAR" y "dimar", eran términos distintos y la señal léxica se perdía por
    mayúsculas, tildes, puntuación y plurales. Aquí se normaliza con
    ``plano`` (minúsculas y sin tildes), se extraen palabras con
    ``\\w+``, se descartan las palabras vacías del español y los tokens de
    una sola letra, y se reduce un plural ligero final ("playas" → "playa",
    "concesiones" → "concesion").

    Medido sobre el corpus congelado (ground truth v0.2, 66 casos) junto con
    el cambio de pesos a BM25 0.8 / vector 0.2: hit@4 de la ruta de producción
    0.690→0.724, MRR 0.549→0.640, artículos 0.088→0.201, normativa 5→7/18.
    La misma función se usa para indexar y para consultar.
    """
    tokens = re.findall(r"\w+", plano(text))
    resultado: list[str] = []
    for token in tokens:
        if token in _STOPWORDS_ES or len(token) == 1:
            continue
        if len(token) > 4 and token.endswith("es"):
            token = token[:-2]
        elif len(token) > 4 and token.endswith("s"):
            token = token[:-1]
        resultado.append(token)
    return resultado


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
    sin evidencia" (``True``). La usa ``GET /api/ready`` (ver
    ``api/main.py``) para comprobar el estado del corpus sin volver a
    consultar Chroma en cada chequeo.
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


def close_retrievers() -> None:
    """Libera los singletons del retriever al apagar la aplicación.

    Cierra la sesión HTTP del cliente de embeddings compartido (``EMBEDDINGS``,
    la única conexión propia que este módulo mantiene abierta) y resetea los
    singletons de módulo (cliente Chroma, vectorstore, índice BM25) a
    ``None`` para que un ``init_retrievers()`` posterior — por ejemplo entre
    pruebas — los reconstruya desde cero. No invoca ningún método privado o
    no documentado del cliente de Chroma: su conexión HTTP se libera junto
    con el objeto en cuanto pierde todas las referencias. Idempotente: llamar
    dos veces no falla (``EMBEDDINGS.close()`` ya lo es, y resetear a
    ``None`` un singleton que ya es ``None`` es un no-op).
    """
    global _chroma_client, _chroma_vectorstore, _bm25_base
    EMBEDDINGS.close()
    _chroma_client = None
    _chroma_vectorstore = None
    _bm25_base = None


# ---------------------------------------------------------------------
# Utilidades: cargar docs de Chroma
# ---------------------------------------------------------------------


def load_all_docs_from_chroma() -> list[Document]:
    """
    Lee todos los documentos de la colección en Chroma usando el cliente
    singleton (evita abrir nuevas conexiones en cada llamada).

    ``ids``/``documents``/``metadatas`` son tres listas paralelas devueltas
    por la misma llamada a Chroma — deben tener exactamente la misma
    longitud. Antes, ``zip(..., strict=False)`` truncaba en silencio a la
    más corta si alguna vez no coincidían (una respuesta corrupta o
    parcial), descartando candidatos sin ningún aviso. Se falla
    explícitamente en su lugar.
    """
    collection = _get_chroma_client().get_collection(name=CHROMA_COLLECTION_NAME)
    raw = collection.get(include=["documents", "metadatas"])

    ids = raw.get("ids", [])
    documents = raw.get("documents", [])
    metadatas = raw.get("metadatas", [])
    if not (len(ids) == len(documents) == len(metadatas)):
        raise RuntimeError(
            "Chroma devolvió longitudes inconsistentes para ids/documents/metadatas "
            f"(ids={len(ids)}, documents={len(documents)}, metadatas={len(metadatas)}) "
            "— no se puede construir el corpus de forma confiable a partir de una "
            "respuesta corrupta o parcial."
        )

    docs: list[Document] = []
    for text, meta, _id in zip(documents, metadatas, ids, strict=True):
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


def _diversificar_sentencias(docs: list[Document], tope: int) -> list[Document]:
    """Partición estable: a partir del fragmento ``tope + 1`` de una misma
    sentencia, los siguientes pasan al final (no se descartan). Solo aplica a
    ``jurisprudencia``; las normas conservan todos sus artículos."""
    vistos: dict[str, int] = {}
    primeros: list[Document] = []
    extra: list[Document] = []
    for doc in docs:
        meta = doc.metadata or {}
        if meta.get("doc_type") != "jurisprudencia":
            primeros.append(doc)
            continue
        clave = str(meta.get("source") or meta.get("title") or doc.page_content)
        vistos[clave] = vistos.get(clave, 0) + 1
        (primeros if vistos[clave] <= tope else extra).append(doc)
    return [*primeros, *extra]


def _es_norma_aplicable(doc: Document, lugares: set[str]) -> bool:
    """Norma nacional, o norma local de un lugar que la consulta menciona.

    Las normas locales de otras ciudades no cuentan: la prioridad territorial
    ya las posterga y la jerarquía no debe devolverlas al frente.
    """
    meta = doc.metadata or {}
    if meta.get("doc_type") != "normativa":
        return False
    lugar = lugar_de_norma(meta)
    return lugar is None or lugar in lugares


def _priorizar_normativa(
    seleccion: list[Document],
    candidatos: Sequence[Document],
    queries: Sequence[str],
    cupos: int,
) -> list[Document]:
    """Jerarquía normativa: la norma va antes que la jurisprudencia.

    1. Si la selección tiene menos de ``cupos`` normas aplicables y quedan
       normas aplicables entre los ``candidatos`` no seleccionados, cada una
       reemplaza a la jurisprudencia peor ubicada de la selección. Nunca
       cambia el tamaño de la selección ni quita normas.
    2. Partición estable: las normas aplicables primero, luego el resto, cada
       grupo en su orden de fusión. Así el modelo lee la norma (REMAC,
       decretos, leyes) antes que las sentencias que la interpretan.
    """
    lugares = lugares_mencionados(queries)
    seleccion = list(seleccion)
    faltan = cupos - sum(_es_norma_aplicable(d, lugares) for d in seleccion)
    if faltan > 0:
        ya = {id(d) for d in seleccion}
        reservas = [d for d in candidatos if id(d) not in ya and _es_norma_aplicable(d, lugares)]
        for norma in reservas[:faltan]:
            juris = [
                i
                for i, d in enumerate(seleccion)
                if (d.metadata or {}).get("doc_type") == "jurisprudencia"
            ]
            if not juris:
                break
            seleccion[juris[-1]] = norma
    normas = [d for d in seleccion if _es_norma_aplicable(d, lugares)]
    resto = [d for d in seleccion if not _es_norma_aplicable(d, lugares)]
    return [*normas, *resto]


class HybridEnsembleRetriever(BaseRetriever):
    """
    Retriever híbrido que combina varios sub-retrievers usando
    Weighted Reciprocal Rank Fusion (RRF).

    Concurrencia: una sola capa. ``ainvoke()`` (usado por el grafo en
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
    c: int = RRF_C  # constante RRF; ver RRF_C para la medición que la fija
    id_key: str | None = "chunk_id"
    max_results: int = 4
    priorizar_territorio: bool = True
    # Tope de fragmentos por sentencia antes del recorte (None = sin tope).
    # Sin él, el top-4 se llenaba con cuatro fragmentos de una misma
    # sentencia. Medido sobre el ground truth v0.2: hit@4 de producción
    # 0.724→0.759, documento en top-20 0.793→0.828, normativa 7→8/18; cuesta
    # artículos 0.201→0.175 (un caso). Las normas no tienen tope.
    fragmentos_por_sentencia: int | None = 1
    # Jerarquía normativa (pedida por el equipo jurídico): la norma aplicable
    # va antes que la jurisprudencia en el contexto, y se le reservan
    # ``cupos_normativa`` puestos si hay normas entre los candidatos. Ver
    # ``_priorizar_normativa`` y CUPOS_NORMATIVA para la medición.
    normativa_primero: bool = True
    cupos_normativa: int = CUPOS_NORMATIVA

    @model_validator(mode="after")
    def _validate_retrievers_and_weights_match(self) -> HybridEnsembleRetriever:
        """Un ``HybridEnsembleRetriever`` con más pesos que retrievers (o
        viceversa) es una configuración estructuralmente inválida: antes de
        este chequeo, ``zip(all_results, self.weights, strict=False)`` en
        ``_fuse()`` truncaba en silencio a la lista más corta, descartando
        candidatos o pesos sin ningún aviso. Falla explícitamente en su
        lugar, en el momento de construcción — antes de que llegue siquiera
        una consulta. No cambia nada para la única configuración que este
        módulo construye hoy (``get_ensemble_retriever()``: siempre 2
        retrievers y 2 pesos, BM25 + vector), así que el ranking sobre una
        configuración válida permanece idéntico.
        """
        if len(self.retrievers) != len(self.weights):
            raise ValueError(
                "HybridEnsembleRetriever: el número de retrievers "
                f"({len(self.retrievers)}) no coincide con el número de pesos "
                f"({len(self.weights)})."
            )
        return self

    def _fuse(
        self,
        all_results: list[list[Document]],
        weights: Sequence[float] | None = None,
        queries: Sequence[str] = (),
    ) -> list[Document]:
        """Fusión RRF ponderada, común a las rutas síncrona, asíncrona y multiconsulta.

        ``weights`` permite reutilizar esta misma fórmula cuando una ruta
        produce varias listas por sub-recuperador (multiconsulta). Si se omite,
        se usan los pesos de la instancia, que es el caso de una sola consulta.

        ``queries`` habilita la prioridad territorial: antes de recortar a
        ``max_results`` se demotan las normas locales de ciudades que las
        consultas no mencionan, de modo que los puestos liberados los ocupan
        los siguientes candidatos. Con ``queries`` vacío no se reordena nada.
        """
        effective_weights = list(self.weights if weights is None else weights)
        if len(all_results) != len(effective_weights):
            raise ValueError(
                "HybridEnsembleRetriever._fuse(): el número de listas de resultados "
                f"({len(all_results)}) no coincide con el número de pesos "
                f"({len(effective_weights)}) — configuración estructural inválida antes "
                "de fusionar."
            )
        scores: dict[str, float] = {}
        doc_by_id: dict[str, Document] = {}

        for docs, w in zip(all_results, effective_weights, strict=False):
            for rank, doc in enumerate(docs, start=1):
                if self.id_key and self.id_key in (doc.metadata or {}):
                    doc_id = str(doc.metadata[self.id_key])
                else:
                    doc_id = doc.page_content

                doc_by_id.setdefault(doc_id, doc)
                scores[doc_id] = scores.get(doc_id, 0.0) + w / (rank + self.c)

        # Se recorre en orden de score descendente. Antes de descartar los
        # candidatos sin contenido alfanumérico (basura estructural del
        # corpus) y de truncar a max_results, se demotan las normas locales de
        # ciudades no mencionadas: así el recorte final se hace sobre el orden
        # territorial y los puestos liberados los ocupan los siguientes
        # candidatos. No afecta a BM25, al vector store, a los pesos ni a k:
        # opera solo sobre el resultado ya fusionado, así que nunca devuelve
        # más de max_results documentos.
        sorted_ids = sorted(scores, key=lambda identifier: scores[identifier], reverse=True)
        ordered_docs = [doc_by_id[doc_id] for doc_id in sorted_ids]
        if self.fragmentos_por_sentencia:
            ordered_docs = _diversificar_sentencias(ordered_docs, self.fragmentos_por_sentencia)
        if self.priorizar_territorio and queries:
            ordered_docs = _priorizar_territorio(ordered_docs, queries)

        candidatos = [d for d in ordered_docs if _has_retrievable_content(d.page_content or "")]
        selected = candidatos[: self.max_results]
        if self.normativa_primero and queries:
            selected = _priorizar_normativa(selected, candidatos, queries, self.cupos_normativa)
        return selected

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        all_results: list[list[Document]] = [r.invoke(query) for r in self.retrievers]
        return self._fuse(all_results, queries=(query,))

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
        return self._fuse(all_results, queries=(query,))

    @staticmethod
    def _normalize_queries(queries: Sequence[str]) -> list[str]:
        """Descarta consultas vacías o de solo espacios y deduplica por orden."""
        normalized: list[str] = []
        seen: set[str] = set()
        for query in queries:
            value = (query or "").strip()
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)
        return normalized

    async def afuse_queries(self, queries: Sequence[str]) -> list[Document]:
        """Recupera con cada consulta y fusiona todas las listas con RRF.

        Cada sub-recuperador recibe cada consulta una sola vez (los duplicados
        y las cadenas vacías se descartan antes de llamar). Todas las llamadas
        se lanzan juntas en un único ``asyncio.gather`` sobre ``ainvoke`` — sin
        ``asyncio.to_thread`` ni ``ThreadPoolExecutor`` anidados — y se fusionan
        con la misma fórmula y el mismo filtro post-fusión que la ruta de una
        sola consulta, aplicando a cada lista el peso del sub-recuperador que
        la produjo.
        """
        normalized = self._normalize_queries(queries)
        if not normalized:
            return []

        all_results = await asyncio.gather(
            *(r.ainvoke(query) for query in normalized for r in self.retrievers)
        )
        # Orden query-major, igual que el productorio de arriba: por cada
        # consulta se repite la secuencia de pesos de self.retrievers.
        weights = list(self.weights) * len(normalized)
        return self._fuse(list(all_results), weights=weights, queries=normalized)


def get_ensemble_retriever(
    k: int = 4,
    k_candidates: int | None = None,
    bm25_weight: float = BM25_WEIGHT,
    vector_weight: float = VECTOR_WEIGHT,
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
