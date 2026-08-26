"""T2.1 — colección vacía sin evidencia ficticia.

``BM25Okapi([])`` lanza ``ZeroDivisionError`` (verificado empíricamente:
divide por la longitud promedio de documento, indefinida con cero
documentos). La versión anterior evitaba ese crash inyectando un documento
placeholder ("sin documentos") en el corpus — pero BM25 podía entonces
devolver ese placeholder como si fuera un fragmento real, fabricando
evidencia. Estas pruebas verifican que ``rank_bm25.BM25Okapi`` nunca se
invoca con un corpus vacío, que ya no existe ningún placeholder, que las
búsquedas sobre un índice vacío devuelven una lista vacía (no basura), y que
el arranque de la app no falla por tener la colección vacía.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from langchain_core.documents import Document

from rag.core import retriever as retriever_module
from rag.core.retriever import BM25Retriever, _get_bm25_base, bm25_index_is_empty


@pytest.fixture(autouse=True)
def _reset_bm25_singleton() -> Iterator[None]:
    """El índice BM25 es un singleton de módulo; se resetea entre pruebas
    para que cada una controle su propia construcción vía monkeypatch."""
    original = retriever_module._bm25_base
    retriever_module._bm25_base = None
    yield
    retriever_module._bm25_base = original


def _boom_bm25okapi(corpus: list[list[str]]) -> None:
    raise AssertionError(f"BM25Okapi no debe invocarse con un corpus vacío (recibido: {corpus!r})")


# ---------------------------------------------------------------------------
# _get_bm25_base() con corpus vacío
# ---------------------------------------------------------------------------


def test_empty_corpus_never_calls_bm25okapi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: [])
    # Si el código llegara a importar/llamar rank_bm25.BM25Okapi, esto falla.
    import rank_bm25

    monkeypatch.setattr(rank_bm25, "BM25Okapi", _boom_bm25okapi)

    base = _get_bm25_base()

    assert base.vectorizer is None
    assert base.docs == []


def test_empty_corpus_index_never_raises_zero_division_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: [])
    # No debe propagar ZeroDivisionError (el bug histórico de BM25Okapi([])).
    _get_bm25_base()


def test_no_placeholder_document_is_fabricated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: [])
    base = _get_bm25_base()
    assert base.docs == []
    assert all(d.page_content != "sin documentos" for d in base.docs)


def test_empty_bm25_index_returns_no_results_instead_of_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: [])
    base = _get_bm25_base()

    results = base.invoke("cualquier consulta")

    assert results == []


def test_bm25_retriever_with_none_vectorizer_returns_empty_directly() -> None:
    """Construcción directa (sin pasar por _get_bm25_base), por si algún
    caller futuro arma un BM25Retriever(vectorizer=None, ...) a mano."""
    retriever = BM25Retriever(vectorizer=None, docs=[], k=5)
    assert retriever.invoke("consulta") == []


# ---------------------------------------------------------------------------
# _get_bm25_base() con corpus no vacío — sin regresión
# ---------------------------------------------------------------------------


def test_nonempty_corpus_still_builds_real_bm25_index(monkeypatch: pytest.MonkeyPatch) -> None:
    docs = [
        Document(page_content="acceso público a la playa", metadata={"id": "1"}),
        Document(page_content="permiso de pesca artesanal", metadata={"id": "2"}),
    ]
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: docs)

    base = _get_bm25_base()

    assert base.vectorizer is not None
    assert base.docs == docs
    # El vectorizador real debe poder responder consultas normalmente.
    results = base.invoke("acceso playa")
    assert len(results) > 0


def test_nonempty_corpus_augments_text_with_keywords_and_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No debe romperse el enriquecimiento de texto (keywords_str + summary)
    que ya existía antes de esta entrega. Se verifica inspeccionando
    directamente el corpus tokenizado que recibe BM25Okapi (en vez de
    confiar en el orden de ranking, poco fiable con corpus de solo 2
    documentos)."""
    docs = [
        Document(
            page_content="concesión de playa",
            metadata={"id": "1", "keywords_str": "dominio marítimo terrestre", "summary": ""},
        ),
        Document(page_content="otro fragmento sin relación", metadata={"id": "2"}),
    ]
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: docs)

    captured_corpus: list[list[str]] = []
    import rank_bm25

    real_bm25okapi = rank_bm25.BM25Okapi

    def _spy(corpus: list[list[str]]) -> object:
        captured_corpus.extend(corpus)
        return real_bm25okapi(corpus)

    monkeypatch.setattr(rank_bm25, "BM25Okapi", _spy)

    _get_bm25_base()

    assert captured_corpus[0] == "concesión de playa dominio marítimo terrestre".split()
    assert captured_corpus[1] == "otro fragmento sin relación".split()


# ---------------------------------------------------------------------------
# bm25_index_is_empty() — gancho interno para T2.5 (readiness)
# ---------------------------------------------------------------------------


def test_bm25_index_is_empty_false_before_initialization() -> None:
    assert retriever_module._bm25_base is None
    assert bm25_index_is_empty() is False


def test_bm25_index_is_empty_true_after_building_with_empty_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: [])
    _get_bm25_base()
    assert bm25_index_is_empty() is True


def test_bm25_index_is_empty_false_after_building_with_real_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = [Document(page_content="algo", metadata={"id": "1"})]
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: docs)
    _get_bm25_base()
    assert bm25_index_is_empty() is False


# ---------------------------------------------------------------------------
# Liveness: init_retrievers() no debe fallar con la colección vacía
# ---------------------------------------------------------------------------


def test_init_retrievers_does_not_crash_with_empty_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retriever_module, "_get_chroma_client", lambda: object())
    monkeypatch.setattr(retriever_module, "_get_chroma_vectorstore", lambda: object())
    monkeypatch.setattr(retriever_module, "load_all_docs_from_chroma", lambda: [])

    retriever_module.init_retrievers()  # no debe lanzar

    assert bm25_index_is_empty() is True
