"""La recuperación se ajusta por entorno y sus listas fijas se contrastan con el corpus.

Tras una actualización del corpus no debería hacer falta tocar código para
re-medir la fusión (variables ``RAG_*`` de ``rag.config``), y si el corpus
trae una norma local de un lugar que ``territorio.LUGARES`` no conoce, una
prueba debe decirlo en vez de que la prioridad territorial falle en silencio.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import rag.config as config
from rag.core import retriever
from rag.core.territorio import LUGARES, NOMBRES_LUGAR, lugar_de_norma, plano

RAG_DIR = Path(__file__).resolve().parents[2]
GOLD_NORMATIVA = RAG_DIR.parent / "data" / "documents" / "gold" / "normativa"

# Palabras que en el título de una norma indican un ámbito local.
_AMBITO_LOCAL = re.compile(r"\b(distrito|municipio|departamento|balneario|alcaldia|gobernacion)\b")


# ── Parámetros de recuperación por entorno ──────────────────────────────────


def test_valores_por_defecto_son_los_medidos():
    assert (config.RETRIEVAL_RRF_C, config.RETRIEVAL_BM25_WEIGHT) == (2, 0.8)
    assert config.RETRIEVAL_VECTOR_WEIGHT == 0.2
    assert config.RETRIEVAL_CUPOS_NORMATIVA == 1
    assert config.RETRIEVAL_FRAGMENTOS_POR_SENTENCIA == 1
    assert config.RETRIEVAL_FRAGMENTOS_POR_NORMA == 1


def test_el_retriever_usa_los_valores_de_config():
    campos = retriever.HybridEnsembleRetriever.model_fields
    assert campos["c"].default == config.RETRIEVAL_RRF_C
    assert campos["cupos_normativa"].default == config.RETRIEVAL_CUPOS_NORMATIVA
    assert campos["fragmentos_por_sentencia"].default == 1
    assert campos["fragmentos_por_norma"].default == 1
    assert (retriever.BM25_WEIGHT, retriever.VECTOR_WEIGHT) == (0.8, 0.2)


@pytest.mark.parametrize(
    ("valor", "tipo", "esperado"),
    [("3", int, 3), (" 0.5 ", float, 0.5), ("", int, 7), ("0", int, 0)],
)
def test_parse_number_acepta_valores_validos(monkeypatch, valor, tipo, esperado):
    monkeypatch.setenv("RAG_PRUEBA_NUMERO", valor)
    assert config._parse_number("RAG_PRUEBA_NUMERO", "7", tipo) == esperado


@pytest.mark.parametrize(
    ("valor", "tipo"), [("dos", int), ("-1", int), ("nan", float), ("1.5", int)]
)
def test_parse_number_falla_nombrando_la_variable(monkeypatch, valor, tipo):
    monkeypatch.setenv("RAG_PRUEBA_NUMERO", valor)
    with pytest.raises(ValueError, match="RAG_PRUEBA_NUMERO"):
        config._parse_number("RAG_PRUEBA_NUMERO", "1", tipo)


def test_las_variables_de_entorno_cambian_el_retriever_sin_tocar_codigo(tmp_path):
    codigo = (
        "from rag.core import retriever as r\n"
        "f = r.HybridEnsembleRetriever.model_fields\n"
        "print(r.RRF_C, r.BM25_WEIGHT, r.VECTOR_WEIGHT, f['cupos_normativa'].default,"
        " f['fragmentos_por_sentencia'].default, f['fragmentos_por_norma'].default)\n"
    )
    vacio = tmp_path / "vacio.env"
    vacio.write_text("", encoding="utf-8")
    entorno = {
        **os.environ,
        "RAG_ENV_FILE": str(vacio),
        "PYTHONPATH": os.pathsep.join([str(RAG_DIR / "backend"), str(RAG_DIR)]),
        "RAG_RRF_C": "60",
        "RAG_BM25_WEIGHT": "0.5",
        "RAG_VECTOR_WEIGHT": "0.5",
        "RAG_CUPOS_NORMATIVA": "2",
        "RAG_FRAGMENTOS_POR_SENTENCIA": "0",
        "RAG_FRAGMENTOS_POR_NORMA": "3",
    }
    salida = subprocess.run(
        [sys.executable, "-c", codigo],
        env=entorno,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert salida.stdout.split() == ["60", "0.5", "0.5", "2", "None", "3"]


def test_sin_tope_por_sentencia_se_mantiene_el_tope_por_norma():
    from langchain_core.documents import Document

    def frag(fuente: str, tipo: str, i: int) -> Document:
        return Document(
            page_content=f"{fuente} {i}",
            metadata={"source": fuente, "doc_type": tipo, "chunk_id": f"{fuente}-{i}"},
        )

    docs = [frag("norma", "normativa", 1), frag("norma", "normativa", 2)]
    docs += [frag("sentencia", "jurisprudencia", 1), frag("sentencia", "jurisprudencia", 2)]
    orden = retriever._diversificar_sentencias(docs, None, 1)
    assert [d.metadata["chunk_id"] for d in orden] == [
        "norma-1",
        "sentencia-1",
        "sentencia-2",
        "norma-2",
    ]


# ── Lugares del corpus frente a ``territorio.LUGARES`` ──────────────────────


def _normas_gold() -> list[dict]:
    metadatos = []
    for path in sorted(GOLD_NORMATIVA.glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            metadatos.append(json.loads(stream.readline())["metadata"])
    return metadatos


def test_toda_norma_local_del_corpus_tiene_lugar_conocido():
    normas = _normas_gold()
    assert normas, f"No hay capa gold de normativa en {GOLD_NORMATIVA}"
    locales = [m for m in normas if _AMBITO_LOCAL.search(plano(str(m.get("title", ""))))]
    assert locales, "Ninguna norma local en el corpus: revisar la expresión _AMBITO_LOCAL"
    sin_lugar = [m["title"] for m in locales if lugar_de_norma(m) is None]
    assert not sin_lugar, (
        "Normas locales sin lugar en rag/core/territorio.py (añadir el lugar y sus "
        f"playas a LUGARES y su nombre a NOMBRES_LUGAR): {sin_lugar}"
    )


def test_cada_lugar_tiene_nombre_legible():
    assert set(NOMBRES_LUGAR) == set(LUGARES)
