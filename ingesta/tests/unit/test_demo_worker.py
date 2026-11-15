"""Regresiones del reset, registro de base y protecciones del arnés AWS."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import chromadb
import pytest

from demo.worker.base_demo import preparar_base, registrar_base
from demo.worker.reset_demo import archivar_objeto, reconciliar_documentos


@pytest.fixture
def colecciones(monkeypatch):
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    cliente = chromadb.EphemeralClient()
    nombre = "atlas_demo_e2e_" + uuid.uuid4().hex
    viva = cliente.create_collection(nombre)
    staging = cliente.create_collection(nombre + "__staging")
    yield cliente, nombre, viva, staging
    for candidata in (nombre, nombre + "__staging"):
        if candidata in [c.name for c in cliente.list_collections()]:
            cliente.delete_collection(candidata)


def sembrar_coleccion(coleccion):
    coleccion.add(
        ids=["demo-1", "base-1"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[{"doc_id": "demo"}, {"doc_id": "base"}],
    )


def sembrar_ficha(estado, estado_ficha):
    ficha = estado / "intake/demo.json"
    instantanea = estado / "intake/instantaneas/demo.jsonl.gz"
    instantanea.parent.mkdir(parents=True)
    ficha.write_text(json.dumps({"estado": estado_ficha}), encoding="utf-8")
    instantanea.write_bytes(b"evidencia")
    return ficha, instantanea


@pytest.mark.parametrize(
    "estado_ficha",
    [
        "publicado",
        "publicando",
        "retirando",
        "error_publicacion",
        "limpieza_pendiente",
        "revision_humana",
        "rechazado",
    ],
)
def test_reset_reconcilia_ambas_colecciones_para_cualquier_estado(
    colecciones, tmp_path, estado_ficha
):
    cliente, nombre, viva, staging = colecciones
    ficha, instantanea = sembrar_ficha(tmp_path, estado_ficha)
    for coleccion in (viva, staging):
        sembrar_coleccion(coleccion)
    assert reconciliar_documentos(cliente, nombre, tmp_path, ["demo"]) == 1
    for coleccion in (viva, staging):
        assert coleccion.get(where={"doc_id": "demo"}, include=[])["ids"] == []
        assert coleccion.get(where={"doc_id": "base"}, include=[])["ids"] == ["base-1"]
    assert not ficha.exists() and not instantanea.exists()


def test_reset_conserva_evidencia_si_quedan_chunks(colecciones, tmp_path, monkeypatch):
    cliente, nombre, viva, staging = colecciones
    ficha, instantanea = sembrar_ficha(tmp_path, "error_publicacion")
    for coleccion in (viva, staging):
        sembrar_coleccion(coleccion)
    eliminar = type(staging).delete

    def borrar(self, **opciones):
        assert ficha.exists() and instantanea.exists()
        if self.name != staging.name:
            eliminar(self, **opciones)

    monkeypatch.setattr(type(staging), "delete", borrar)
    with pytest.raises(RuntimeError, match="Quedan chunks"):
        reconciliar_documentos(cliente, nombre, tmp_path, ["demo"])
    assert ficha.exists() and instantanea.exists()


def test_reset_sin_colecciones_borra_solo_evidencia_local(tmp_path, colecciones):
    ficha, instantanea = sembrar_ficha(tmp_path, "rechazado")
    assert (
        reconciliar_documentos(colecciones[0], "ausente_" + uuid.uuid4().hex, tmp_path, ["demo"])
        == 0
    )
    assert not ficha.exists() and not instantanea.exists()


@pytest.mark.parametrize("versionado", [True, False])
def test_archivo_s3_usa_copia_gestionada_y_borra_version_precisa(versionado):
    s3 = Mock()
    cabecera = {"ETag": "original", "ContentLength": 6_000_000_000}
    if versionado:
        cabecera["VersionId"] = "v1"
    s3.head_object.return_value = cabecera
    archivar_objeto(s3, "bucket", "processed/doc/original.pdf", "archive/doc.pdf")
    origen = {"Bucket": "bucket", "Key": "processed/doc/original.pdf"}
    if versionado:
        origen["VersionId"] = "v1"
    s3.copy.assert_called_once_with(
        origen, "bucket", "archive/doc.pdf", ExtraArgs={"CopySourceIfMatch": "original"}
    )
    s3.copy_object.assert_not_called()
    s3.delete_object.assert_called_once_with(**origen)


def test_archivo_s3_conserva_sustitucion_sin_versionado():
    s3 = Mock()
    s3.head_object.side_effect = [
        {"ETag": "original", "ContentLength": 10},
        {"ETag": "nuevo", "ContentLength": 10},
    ]
    with pytest.raises(RuntimeError, match="cambió"):
        archivar_objeto(s3, "bucket", "processed/doc/a.pdf", "archive/a.pdf")
    s3.delete_object.assert_not_called()


def test_registrar_base_solo_incluye_solicitados_y_estados_terminales(tmp_path):
    estado = tmp_path / "estado"
    (estado / "intake").mkdir(parents=True)
    for doc, estado_ficha in [
        ("a", "publicado"),
        ("b", "revision_humana"),
        ("c", "rechazado"),
        ("ajeno", "publicado"),
    ]:
        (estado / f"intake/{doc}.json").write_text(
            json.dumps({"estado": estado_ficha}), encoding="utf-8"
        )
    destino = tmp_path / "base_hashes.txt"
    registrar_base(estado, ["b", "a", "c", "a"], destino)
    assert destino.read_text() == "a\nb\nc\n"


@pytest.mark.parametrize("estado_ficha", [None, "publicando", "error_publicacion"])
def test_registro_fallido_conserva_base_anterior(tmp_path, estado_ficha):
    (tmp_path / "intake").mkdir()
    if estado_ficha:
        (tmp_path / "intake/a.json").write_text(
            json.dumps({"estado": estado_ficha}), encoding="utf-8"
        )
    destino = tmp_path / "base_hashes.txt"
    destino.write_text("anterior\n")
    with pytest.raises(ValueError):
        registrar_base(tmp_path, ["a"], destino)
    assert destino.read_text() == "anterior\n"


def test_preparar_base_exige_todos_los_sufijos_y_evita_colisiones(tmp_path):
    mapa = {}
    for categoria, cuerpo, sufijo in [("normas", b"uno", "abcd"), ("sentencias", b"dos", "efgh")]:
        ruta = tmp_path / f"data/documents/raw/{categoria}/igual.pdf"
        ruta.parent.mkdir(parents=True)
        ruta.write_bytes(cuerpo)
        mapa[hashlib.sha256(cuerpo).hexdigest()] = sufijo
    mapping = tmp_path / "ingesta/benchmarks/demo_aws/sufijos_raw.json"
    mapping.parent.mkdir(parents=True)
    mapping.write_text(json.dumps(mapa), encoding="utf-8")
    buzon = tmp_path / "buzon"
    for sufijos in ([], ["abcd", "ausente"]):
        with pytest.raises(ValueError):
            preparar_base(tmp_path, buzon, sufijos)
        assert not buzon.exists()
    hashes = preparar_base(tmp_path, buzon, ["abcd", "efgh"])
    assert hashes == sorted(mapa)
    assert len(list(buzon.glob("*.pdf"))) == 2
    assert {json.loads(p.read_text())["categoria"] for p in buzon.glob("*.meta.json")} == {
        "normas",
        "sentencias",
    }


def test_registro_vacio_no_reemplaza_base(tmp_path):
    destino = tmp_path / "base_hashes.txt"
    destino.write_text("anterior\n")
    with pytest.raises(ValueError, match="vacía"):
        registrar_base(tmp_path, [], destino)
    assert destino.read_text() == "anterior\n"


@pytest.fixture
def arnes_aws():
    ruta = Path(__file__).resolve().parents[2] / "benchmarks/demo_aws/e2e_aws.py"
    spec = importlib.util.spec_from_file_location("e2e_aws", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("destino", ["viva", "staging"])
def test_e2e_aborta_antes_de_borrar_trabajo_si_coleccion_tiene_datos(
    arnes_aws, colecciones, tmp_path, monkeypatch, destino
):
    cliente, nombre, viva, staging = colecciones
    sembrar_coleccion(viva if destino == "viva" else staging)
    monkeypatch.setattr(chromadb, "HttpClient", lambda **_: cliente)
    monkeypatch.setattr(arnes_aws, "COLECCION", nombre)
    (tmp_path / arnes_aws.MARCADOR).touch()
    evidencia = tmp_path / "resultado_anterior.txt"
    evidencia.write_text("conservar")
    arnes = arnes_aws.E2E.__new__(arnes_aws.E2E)
    arnes.t = tmp_path
    arnes.a = SimpleNamespace(puerto=8000, recrear_coleccion=False)
    with pytest.raises(SystemExit, match="contiene datos"):
        arnes.correr()
    assert evidencia.read_text() == "conservar"


def test_e2e_coleccion_ausente_o_vacia_admisible_y_recreacion_limitada(arnes_aws, colecciones):
    cliente, nombre, viva, staging = colecciones
    arnes_aws.preparar_coleccion(cliente, "ausente_" + uuid.uuid4().hex)
    arnes_aws.preparar_coleccion(cliente, nombre)
    for coleccion in (viva, staging):
        sembrar_coleccion(coleccion)
    with pytest.raises(SystemExit, match="solo permite"):
        arnes_aws.preparar_coleccion(cliente, "produccion", recrear=True)
    assert viva.count() == staging.count() == 2
    arnes_aws.preparar_coleccion(cliente, nombre, recrear=True)
    nombres = {c.name for c in cliente.list_collections()}
    assert nombre not in nombres and nombre + "__staging" not in nombres


@pytest.mark.parametrize("protegida", ["repo", "documents", "worker"])
def test_e2e_valida_rutas_protegidas_antes_de_cualquier_borrado(
    arnes_aws, tmp_path, monkeypatch, protegida
):
    repo = tmp_path / "repo"
    monkeypatch.setattr(arnes_aws, "REPO", repo)
    arnes = arnes_aws.E2E.__new__(arnes_aws.E2E)
    arnes.t = {
        "repo": repo,
        "documents": repo / "data/documents",
        "worker": Path("/var/lib/atlas"),
    }[protegida]
    with pytest.raises(SystemExit, match="se solapa"):
        arnes.correr()
