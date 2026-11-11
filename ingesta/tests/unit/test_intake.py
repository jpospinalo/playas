"""Entrada autónoma con PDFs sintéticos, OCR sembrado y Chroma en memoria, sin red."""

from __future__ import annotations

import csv
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import chromadb
import fitz
import pytest
import yaml

from ingest.offline.__main__ import main
from ingest.offline.extract import EXTRACTOR_VERSION, sha256_file
from ingest.offline.intake import Intake
from ingest.offline.intake_safety import (
    ConfiguracionInvalida,
    cargar_destinos,
    clasificar,
    nombre_seguro,
    simhash_shingles,
    validar_destino,
)
from ingest.offline.publish import ChromaPublisher
from ingest.offline.storage import writer_lock
from ingest.offline_embeddings import FakeBatchEmbeddings

TEXTO = (
    "CONSEJO DE ESTADO\nMagistrado ponente: JUAN PEREZ\n"
    "Radicado: 47001-23-33-000-2020-00123-01\nSanta Marta, 12 de marzo de 2024\n"
    "ANTECEDENTES\nEl acceso público a las playas.\nCONSIDERACIONES\n"
    + "Las playas son bienes de uso público. " * 14
    + "\nRESUELVE\nSe protege el acceso."
)
NORMA = (
    "LEY 123 DE 2024\nEL CONGRESO DE COLOMBIA\nDECRETA:\nARTÍCULO 1. Acceso público.\n"
    + "Se protege el acceso de las personas a las playas. " * 12
)


def crear_pdf(ruta, texto=TEXTO, *, cifrado=False, paginas=1):
    with fitz.open() as pdf:
        for _ in range(paginas):
            pagina = pdf.new_page()
            pagina.insert_textbox(fitz.Rect(30, 30, 565, 810), texto, fontsize=10)
        opciones = (
            {"encryption": fitz.PDF_ENCRYPT_AES_256, "owner_pw": "prueba", "user_pw": "prueba"}
            if cifrado
            else {}
        )
        pdf.save(ruta, **opciones)
    return ruta


@pytest.fixture
def sistema(tmp_path, monkeypatch):
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")
    monkeypatch.setenv("ATLAS_CHROMA_LOCK_DIR", str(tmp_path / "chroma_locks"))
    args = SimpleNamespace(
        command="intake",
        collection="bench_intake_pruebas",
        host="127.0.0.1",
        port=8000,
        fake_embeddings=True,
        destinos=None,
        policy=None,
        intervalo=1,
        batch_size=16,
        chunker="legacy",
        token_budget=512,
        from_stage=None,
        dry_run=False,
        state=tmp_path / "estado",
        cache=tmp_path / "cache",
        layers_root=tmp_path / "capas",
        raw_root=tmp_path / "raw",
        inbox=tmp_path / "inbox",
        ollama="http://localhost:11434",
        allow_remote_ollama=False,
    )
    args.inbox.mkdir()
    cliente = chromadb.EphemeralClient()
    # Una colección distinta por prueba; el cliente efímero comparte el proceso.
    args.collection = "bench_intake_" + tmp_path.name.replace("-", "_")[:55]

    def fabrica(nombre, huella, port, **opciones):
        return ChromaPublisher(nombre, huella, port, client=cliente, **opciones)

    def prohibido(*a, **k):
        raise AssertionError("La prueba no permite red ni llamadas LLM")

    monkeypatch.setattr(socket.socket, "connect", prohibido)
    return args, cliente, fabrica


def ejecutar(sistema, **opciones):
    args, cliente, fabrica = sistema
    for campo, valor in opciones.items():
        setattr(args, campo, valor)
    return Intake(args, fabrica_publicador=fabrica).run()


def fichas(sistema):
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((sistema[0].state / "intake").glob("*.json"))
    ]


@pytest.mark.parametrize(
    "categoria,texto,decision",
    [
        (None, TEXTO, "aceptado"),
        (
            None,
            "CONSEJO DE ESTADO\n" + "El acceso a las playas debe protegerse. " * 16,
            "aceptado_con_advertencias",
        ),
        (None, "Documento sin encabezado. " * 20, "revision_humana"),
        (None, "Texto corto.", "rechazado"),
        ("normativa", NORMA, "aceptado_con_advertencias"),
    ],
)
def test_decisiones_reales(sistema, categoria, texto, decision):
    args, cliente, _ = sistema
    pdf = crear_pdf(args.inbox / "documento.pdf", texto)
    if categoria:
        pdf.with_name(pdf.name + ".meta.json").write_text(
            json.dumps({"categoria": categoria}), encoding="utf-8"
        )
    assert ejecutar(sistema) == 0
    ficha = fichas(sistema)[0]
    assert ficha["decision"] == decision
    if decision.startswith("aceptado"):
        assert ficha["estado"] == "publicado", ficha["motivos"]
        assert len(ficha["embeddings"]) > 0
        assert cliente.get_collection(args.collection).count() == len(ficha["chunks"])
        assert (args.raw_root / nombre_seguro(ficha["doc_id"])).read_bytes() == pdf.read_bytes()
    else:
        assert not args.raw_root.exists()
        assert not (args.cache / "bench_embeddings.sqlite").exists()
    assert pdf.exists()


@pytest.mark.parametrize(
    "coleccion", ["v1", "atlas_v1", "rag_playas", "rag_playas_magdalena", "otra", "bench_insegura"]
)
def test_destino_rechazado_antes_del_inbox(sistema, coleccion, monkeypatch):
    args, _, fabrica = sistema
    args.collection = coleccion
    monkeypatch.setattr(Path, "iterdir", lambda *a: pytest.fail("No debe leer el inbox"))
    with pytest.raises(ConfiguracionInvalida, match="protegido"):
        Intake(args, fabrica_publicador=fabrica)
    assert main(["intake", "--collection", coleccion]) == 3


@pytest.mark.parametrize(
    "host", ["produccion.example", "192.168.1.1", "0.0.0.0", "https://127.0.0.1"]
)
def test_host_no_loopback(sistema, host):
    args, _, fabrica = sistema
    args.host = host
    with pytest.raises(ConfiguracionInvalida, match="host"):
        Intake(args, fabrica_publicador=fabrica)
    assert not args.state.exists()


def test_preparacion_y_hosts_protegidos():
    destinos = cargar_destinos()
    destinos["colecciones_protegidas"].append("bench_intake_caso__staging")
    with pytest.raises(ConfiguracionInvalida, match="staging"):
        validar_destino("bench_intake_caso", "127.0.0.1", destinos)
    destinos["hosts_protegidos"] = ["127.0.0.1"]
    with pytest.raises(ConfiguracionInvalida, match="host"):
        validar_destino("bench_intake_otro", "localhost", destinos)


@pytest.mark.parametrize(
    "caso", ["no_pdf", "cifrado", "truncado", "corrupto", "vacio", "desmesurado", "paginas"]
)
def test_pdf_no_confiable(sistema, caso):
    args, _, _ = sistema
    pdf = args.inbox / "entrada.pdf"
    if caso == "no_pdf":
        pdf.write_bytes(b"no es un pdf")
    elif caso == "corrupto":
        pdf.write_bytes(b"%PDF-1.4\ncontenido corrupto\n%%EOF")
    elif caso == "vacio":
        pdf.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
        )
    else:
        crear_pdf(pdf, cifrado=caso == "cifrado", paginas=2 if caso == "paginas" else 1)
        if caso == "truncado":
            pdf.write_bytes(pdf.read_bytes()[:-100])
    if caso in {"desmesurado", "paginas"}:
        destinos = cargar_destinos()
        destinos["tamano_maximo_bytes" if caso == "desmesurado" else "paginas_maximas"] = 1
        args.destinos = args.inbox.parent / "destinos.yaml"
        args.destinos.write_text(yaml.safe_dump(destinos), encoding="utf-8")
    antes = pdf.read_bytes()
    assert ejecutar(sistema) == 0
    assert fichas(sistema)[0]["decision"] == "rechazado"
    assert pdf.read_bytes() == antes


@pytest.mark.parametrize(
    "nombre", ["../malicioso", "..\\..\\malicioso", "malo\x00\x01", "x" * 4000]
)
def test_nombre_hostil_no_participa_en_rutas(nombre):
    import hashlib

    seguro = nombre_seguro(hashlib.sha256(nombre.encode()).hexdigest())
    assert len(seguro) == 68 and "/" not in seguro and "\\" not in seguro and ".." not in seguro


def test_firma_sin_extension_duplicado_y_renombrado(sistema, monkeypatch, capsys):
    args, cliente, _ = sistema
    pdf = crear_pdf(args.inbox / "documento.bin")
    assert ejecutar(sistema) == 0
    ficha = fichas(sistema)[0]
    pdf.rename(args.inbox / "renombrado.bin")
    (args.inbox / "copia.bin").write_bytes((args.inbox / "renombrado.bin").read_bytes())
    monkeypatch.setattr(Intake, "_analizar", lambda *a: pytest.fail("No debe reconstruir capas"))
    monkeypatch.setattr(
        Intake, "_embeddings", lambda *a: pytest.fail("No debe calcular embeddings")
    )
    assert ejecutar(sistema) == 0
    assert len(fichas(sistema)) == 1
    assert cliente.get_collection(args.collection).count() == len(ficha["chunks"])
    assert "sin cambios" in capsys.readouterr().out


def test_firma_pdf_tras_bytes_iniciales_se_acepta_y_lo_demas_se_rechaza(sistema):
    # Regresión E2E: dos PDF reales del corpus empiezan con «\t\n» antes de %PDF-.
    args, _, _ = sistema
    pdf = crear_pdf(args.inbox / "con_prefijo.pdf")
    pdf.write_bytes(b"\t\n" + pdf.read_bytes())
    (args.inbox / "falso.pdf").write_bytes(b"MZ" + b"\0" * 2000 + b"%%EOF")
    assert ejecutar(sistema) == 0
    por_estado = {f["estado"]: f for f in fichas(sistema)}
    assert "publicado" in por_estado
    assert por_estado["rechazado"]["motivos"] == ["Firma inválida: no es un PDF (%PDF-)"]


def test_cuasi_duplicado_no_se_fusiona(sistema):
    args, cliente, _ = sistema
    crear_pdf(args.inbox / "primero.pdf")
    assert ejecutar(sistema) == 0
    crear_pdf(args.inbox / "segundo.pdf")  # Otro PDF, distinto hash, mismo silver.
    assert ejecutar(sistema) == 0
    resultados = fichas(sistema)
    assert sorted(f["estado"] for f in resultados) == ["publicado", "revision_humana"]
    revisado = next(f for f in resultados if f["estado"] == "revision_humana")
    assert any("posible versión nueva de" in m for m in revisado["motivos"])
    with (args.state / "review_queue.csv").open(encoding="utf-8") as entrada:
        assert len(list(csv.DictReader(entrada))) == 1
    assert ejecutar(sistema) == 0
    assert cliente.get_collection(args.collection + "__staging").count() == 0


def test_correccion_lateral_y_csv_resuelven_categoria(sistema):
    args, _, _ = sistema
    pdf = crear_pdf(args.inbox / "dudoso.pdf", "Regulación local. " * 30)
    assert ejecutar(sistema) == 0
    assert "categoría dudosa" in fichas(sistema)[0]["motivos"]
    (args.inbox / "metadata_intake.csv").write_text(
        f"hash,categoria\n{sha256_file(pdf)},normativa\n", encoding="utf-8"
    )
    assert ejecutar(sistema) == 0
    assert "categoría dudosa" not in fichas(sistema)[0]["motivos"]
    pdf.with_name(pdf.name + ".meta.json").write_text(
        '{"categoria":"jurisprudencia"}', encoding="utf-8"
    )
    assert ejecutar(sistema) == 0
    assert len(fichas(sistema)) == 1
    assert fichas(sistema)[0]["clasificacion"]["origen"] == "correccion_manual"


def test_reanudacion_embeddings_y_huerfanos(sistema, monkeypatch):
    args, cliente, fabrica = sistema
    texto_largo = (
        TEXTO
        + "\n"
        + "\n".join(
            f"Fundamento {numero}: se garantiza el acceso público y la protección de la costa."
            for numero in range(24)
        )
    )
    crear_pdf(args.inbox / "fallo.pdf", texto_largo)
    original = FakeBatchEmbeddings.embed

    def fallo_parcial(self, textos):
        original(self, textos[:1])
        raise RuntimeError("Fallo simulado después de persistir un vector")

    with monkeypatch.context() as contexto:
        contexto.setattr(FakeBatchEmbeddings, "embed", fallo_parcial)
        assert ejecutar(sistema) == 2
    ficha = fichas(sistema)[0]
    assert ficha["estado"] == "error_publicacion"
    viva = cliente.get_collection(args.collection)
    assert viva.count() == 0
    assert ejecutar(sistema) == 0
    ficha = fichas(sistema)[0]
    assert ficha["estado"] == "publicado"
    assert len(ficha["chunks"]) > 1
    assert ficha["embeddings"]["nuevos"] > 0
    assert ficha["embeddings"]["nuevos"] < len(ficha["chunks"])
    extra = {**ficha["chunks"][0], "id": "huerfano"}
    with FakeCierre(args.cache) as embedder:
        fabrica(args.collection, ficha["config_hash"], 8000, fake_embeddings=True).upsert_document(
            ficha["doc_id"], [extra], embedder.embed([extra["document"]])
        )
    assert ejecutar(sistema) == 0
    assert set(viva.get(include=[])["ids"]) == {c["id"] for c in ficha["chunks"]}


class FakeCierre:
    def __init__(self, cache):
        self.embedder = FakeBatchEmbeddings(cache / "bench_embeddings.sqlite")

    def __enter__(self):
        return self.embedder

    def __exit__(self, *args):
        self.embedder.close()


def test_canario_fallido_revierte_y_continua(sistema, monkeypatch):
    args, cliente, _ = sistema
    crear_pdf(args.inbox / "uno.pdf")
    crear_pdf(args.inbox / "dos.pdf", NORMA)
    original = Intake._verificar
    fallos = []

    def canario(self, publicador, doc_id, chunks, vectores=None):
        if vectores is not None and not fallos:
            fallos.append(doc_id)
            raise RuntimeError("Consulta canario fallida")
        return original(self, publicador, doc_id, chunks, vectores)

    monkeypatch.setattr(Intake, "_verificar", canario)
    assert ejecutar(sistema) == 2
    resultados = fichas(sistema)
    assert sorted(f["estado"] for f in resultados) == ["error_publicacion", "publicado"]
    for nombre in (args.collection, args.collection + "__staging"):
        assert (
            cliente.get_collection(nombre).get(where={"doc_id": fallos[0]}, include=[])["ids"] == []
        )


def test_retire_conserva_y_no_resucita(sistema):
    args, cliente, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    ficha = fichas(sistema)[0]
    assert ejecutar(sistema, command="retire", doc_id=ficha["doc_id"]) == 0
    assert fichas(sistema)[0]["estado"] == "retirado"
    assert (args.layers_root / "gold" / (ficha["doc_id"] + ".jsonl")).exists()
    assert ejecutar(sistema, command="intake") == 0
    assert cliente.get_collection(args.collection).count() == 0


def instantanea(raiz):
    return {
        p.relative_to(raiz).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in raiz.rglob("*")
        if p.is_file()
    }


def test_dry_run_sin_efectos(sistema):
    args, cliente, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    antes = instantanea(args.inbox.parent)
    assert ejecutar(sistema, dry_run=True) == 0
    assert instantanea(args.inbox.parent) == antes
    assert ejecutar(sistema, dry_run=False) == 0
    antes = instantanea(args.inbox.parent)
    assert ejecutar(sistema, dry_run=True) == 0
    assert instantanea(args.inbox.parent) == antes


def test_dos_escritores_fallan_limpio(sistema):
    args, _, _ = sistema
    with writer_lock(args.state), pytest.raises(RuntimeError, match="escritor"):
        ejecutar(sistema)
    assert ejecutar(sistema) == 0


def test_recuperacion_bloqueo_tras_muerte(tmp_path):
    raiz = Path(__file__).resolve().parents[2]
    script = "from ingest.offline.storage import writer_lock; import os,sys;\nwith writer_lock(sys.argv[1]): os._exit(9)"
    proceso = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], cwd=raiz, capture_output=True
    )
    assert proceso.returncode == 9
    with writer_lock(tmp_path):
        assert (tmp_path / ".writer.lock").exists()
    assert not (tmp_path / ".writer.lock").exists()


def test_exportar_verificar_y_manipulacion(sistema):
    args, _, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    destino = args.inbox.parent / "paquete.jsonl.gz"
    assert (
        main(
            [
                "--state",
                str(args.state),
                "--cache",
                str(args.cache),
                "--layers-root",
                str(args.layers_root),
                "--collection",
                args.collection,
                "export",
                str(destino),
            ]
        )
        == 0
    )
    assert main(["verify-export", str(destino)]) == 0
    manifiesto = json.loads(
        destino.with_name(destino.name + ".manifest.json").read_text(encoding="utf-8")
    )
    assert manifiesto["archivos"] == {destino.name: sha256_file(destino)}
    destino.write_bytes(destino.read_bytes() + b"alterado")
    assert main(["verify-export", str(destino)]) == 2


def test_from_stage_no_reextrae(sistema):
    args, _, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    bronze = instantanea(args.layers_root / "bronze")
    assert ejecutar(sistema, from_stage="silver") == 0
    assert instantanea(args.layers_root / "bronze") == bronze


def test_ocr_sembrado_sin_tesseract(sistema):
    args, _, _ = sistema
    pdf = crear_pdf(args.inbox / "escaneado.pdf", "")
    doc_id = sha256_file(pdf)
    ocr = args.cache / "ocr" / f"{doc_id}-0-{EXTRACTOR_VERSION}.txt"
    ocr.parent.mkdir(parents=True)
    ocr.write_text(TEXTO, encoding="utf-8")
    ocr.with_suffix(".confidence.json").write_text("99.0", encoding="utf-8")
    assert ejecutar(sistema) == 0
    ficha = fichas(sistema)[0]
    assert ficha["estado"] == "publicado", ficha["motivos"]
    assert ficha["senales"]["paginas_ocr"] == 1


def test_simhash_y_clasificacion():
    assert simhash_shingles("las playas son públicas") == simhash_shingles(
        "LAS PLAYAS SON PUBLICAS"
    )
    assert clasificar({"raw_pages": [NORMA]})["categoria"] == "normativa"
    assert clasificar({"raw_pages": [TEXTO]})["categoria"] == "jurisprudencia"


def test_notificacion_es_solo_archivo(sistema):
    args, _, _ = sistema
    destinos = cargar_destinos()
    gancho = args.inbox.parent / "avisos.jsonl"
    destinos["gancho_notificacion"] = str(gancho)
    args.destinos = args.inbox.parent / "destinos.yaml"
    args.destinos.write_text(yaml.safe_dump(destinos), encoding="utf-8")
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    assert len(gancho.read_text(encoding="utf-8").splitlines()) == 1
    assert json.loads(gancho.read_text(encoding="utf-8"))["llm_api_calls"] == 0


@pytest.mark.parametrize(
    "caso", ["yaml", "umbral", "prefijo", "host_yaml", "ollama", "intervalo", "raw_largo", "raw_v1"]
)
def test_configuracion_invalida_antes_de_entrar(sistema, caso, monkeypatch):
    args, _, fabrica = sistema
    if caso == "yaml":
        args.destinos = args.inbox.parent / "mal.yaml"
        args.destinos.write_text("campo: [\n", encoding="utf-8")
    elif caso == "umbral":
        from ingest.offline.policy import cargar_politica

        politica = cargar_politica()
        politica["revision"]["ocr_confianza_media_minima"] = "incorrecto"
        args.policy = args.inbox.parent / "politica.yaml"
        args.policy.write_text(yaml.safe_dump(politica), encoding="utf-8")
    elif caso in {"prefijo", "host_yaml"}:
        destinos = cargar_destinos()
        destinos["prefijos_permitidos" if caso == "prefijo" else "hosts_chroma_permitidos"] = [
            "cualquiera_" if caso == "prefijo" else "produccion.example"
        ]
        args.destinos = args.inbox.parent / "destinos.yaml"
        args.destinos.write_text(yaml.safe_dump(destinos), encoding="utf-8")
    elif caso == "ollama":
        args.ollama = "http://remoto.example:11434"
    elif caso == "intervalo":
        args.intervalo = 0
    elif caso == "raw_largo":
        args.raw_root = args.inbox.parent / ("x" * 190)
    elif caso == "raw_v1":
        args.raw_root = args.inbox.parent / "data/documents/gold"
    monkeypatch.setattr(Path, "iterdir", lambda *a: pytest.fail("No debe leer entradas"))
    with pytest.raises(ConfiguracionInvalida):
        Intake(args, fabrica_publicador=fabrica)
    assert not args.state.exists()


def test_raw_por_defecto_y_guardias_v1_siguen_activas(sistema):
    from ingest.offline.storage import atomic_bytes

    args, _, _ = sistema
    args.raw_root = args.inbox.parent / "data/documents/raw"
    crear_pdf(args.inbox / "seguro.pdf")
    assert ejecutar(sistema) == 0
    assert len(list(args.raw_root.glob("*.pdf"))) == 1
    with pytest.raises(ValueError, match="protegida"):
        atomic_bytes(args.raw_root / "intruso.pdf", b"no autorizado")


def test_timeout_no_detiene_el_siguiente(sistema, monkeypatch):
    args, _, _ = sistema
    crear_pdf(args.inbox / "a.pdf")
    crear_pdf(args.inbox / "b.pdf", NORMA)
    original = subprocess.run
    intentos = []

    def fallar_una_vez(*a, **k):
        if not intentos:
            intentos.append(1)
            raise subprocess.TimeoutExpired(a[0], 1)
        return original(*a, **k)

    monkeypatch.setattr(subprocess, "run", fallar_una_vez)
    assert ejecutar(sistema) == 2
    assert sorted(f["estado"] for f in fichas(sistema)) == ["error_documento", "publicado"]
    assert any("Tiempo límite" in m for f in fichas(sistema) for m in f["motivos"])


@pytest.mark.parametrize("defecto", ["dimension", "nan", "infinito", "booleano", "digest"])
def test_embeddings_invalidos_nunca_se_publican(sistema, monkeypatch, defecto):
    args, cliente, fabrica = sistema
    crear_pdf(args.inbox / "primero.pdf")
    crear_pdf(args.inbox / "segundo.pdf", NORMA)
    original = FakeBatchEmbeddings.embed

    def vectores_invalidos(self, textos):
        vectores = original(self, textos)
        if defecto == "dimension":
            vectores[0] = vectores[0][:-1]
        else:
            vectores[0][0] = {"nan": float("nan"), "infinito": float("inf"), "booleano": True}[
                defecto
            ]
        return vectores

    def fabrica_embeddings(cache):
        resultado = FakeBatchEmbeddings(cache / "bench_embeddings.sqlite")
        resultado.digest = "digest_incorrecto"
        return resultado

    if defecto == "digest":
        entrada = Intake(args, fabrica_publicador=fabrica, fabrica_embeddings=fabrica_embeddings)
        assert entrada.run() == 2
    else:
        monkeypatch.setattr(FakeBatchEmbeddings, "embed", vectores_invalidos)
        assert ejecutar(sistema) == 2
    assert all(f["estado"] == "error_publicacion" for f in fichas(sistema))
    assert cliente.get_collection(args.collection).count() == 0
    assert cliente.get_collection(args.collection + "__staging").count() == 0


def test_interrupcion_tras_preparacion_reanuda_sin_huerfanos(sistema, monkeypatch):
    args, cliente, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    original = ChromaPublisher.upsert_document

    def interrumpir(self, doc_id, records, vectors):
        original(self, doc_id, records, vectors)
        if self.collection_name.endswith("__staging"):
            raise KeyboardInterrupt("Simular cierre abrupto")

    with monkeypatch.context() as contexto:
        contexto.setattr(ChromaPublisher, "upsert_document", interrumpir)
        with pytest.raises(KeyboardInterrupt):
            ejecutar(sistema)
    ficha = fichas(sistema)[0]
    assert ficha["estado"] == "publicando" and ficha["publicacion_pendiente"]
    assert cliente.get_collection(args.collection + "__staging").count() > 0
    assert ejecutar(sistema) == 0
    ficha = fichas(sistema)[0]
    assert ficha["estado"] == "publicado"
    assert ficha["embeddings"]["nuevos"] == 0
    assert cliente.get_collection(args.collection + "__staging").count() == 0
    assert set(cliente.get_collection(args.collection).get(include=[])["ids"]) == {
        c["id"] for c in ficha["chunks"]
    }


def test_canario_real_fallido_en_viva_revierte(sistema, monkeypatch):
    from chromadb.api.models.Collection import Collection

    args, cliente, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    original = Collection.query

    def respuesta_erronea(self, *a, **k):
        if self.name == args.collection:
            return {"ids": [["chunk_incorrecto"]]}
        return original(self, *a, **k)

    monkeypatch.setattr(Collection, "query", respuesta_erronea)
    assert ejecutar(sistema) == 2
    assert cliente.get_collection(args.collection).count() == 0
    assert cliente.get_collection(args.collection + "__staging").count() == 0
    assert any("canario" in m for m in fichas(sistema)[0]["motivos"])


def test_retiro_interrumpido_se_termina_y_no_publica(sistema, monkeypatch):
    args, cliente, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    doc_id = fichas(sistema)[0]["doc_id"]
    original = ChromaPublisher.delete_document

    def interrumpir(self, doc_id):
        original(self, doc_id)
        raise KeyboardInterrupt("Interrupción del retiro")

    with monkeypatch.context() as contexto:
        contexto.setattr(ChromaPublisher, "delete_document", interrumpir)
        with pytest.raises(KeyboardInterrupt):
            ejecutar(sistema, command="retire", doc_id=doc_id)
    assert fichas(sistema)[0]["accion_pendiente"] == "retirar"
    assert ejecutar(sistema, command="intake") == 0
    assert fichas(sistema)[0]["estado"] == "retirado"
    assert cliente.get_collection(args.collection).count() == 0


def test_exportacion_detecta_manifiesto_inconsistente(sistema):
    args, _, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    paquete = args.inbox.parent / "paquete.jsonl.gz"
    assert (
        main(
            [
                "--state",
                str(args.state),
                "--cache",
                str(args.cache),
                "--layers-root",
                str(args.layers_root),
                "--collection",
                args.collection,
                "export",
                str(paquete),
            ]
        )
        == 0
    )
    lateral = paquete.with_name(paquete.name + ".manifest.json")
    datos = json.loads(lateral.read_text(encoding="utf-8"))
    datos["records"] += 1
    lateral.write_text(json.dumps(datos), encoding="utf-8")
    assert main(["verify-export", str(paquete)]) == 2


def test_registro_de_fases_y_reutilizacion(sistema):
    args, _, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    ficha = fichas(sistema)[0]
    for fase in (
        "bronze",
        "silver",
        "gold",
        "politica",
        "embeddings",
        "preparacion",
        "publicacion",
    ):
        assert ficha["fases"][fase]["estado"] == "completada"
        assert ficha["tiempos"][fase] >= 0
    assert ejecutar(sistema, from_stage="gold") == 0
    assert fichas(sistema)[0]["fases"]["bronze"]["accion"].startswith("Reutilizada")


def test_cli_dry_run_acepta_opciones_y_no_tiene_efectos(sistema):
    args, _, _ = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    antes = instantanea(args.inbox.parent)
    assert (
        main(
            [
                "intake",
                "--collection",
                args.collection,
                "--inbox",
                str(args.inbox),
                "--raw-root",
                str(args.raw_root),
                "--state",
                str(args.state),
                "--cache",
                str(args.cache),
                "--layers-root",
                str(args.layers_root),
                "--once",
                "--fake-embeddings",
                "--dry-run",
            ]
        )
        == 0
    )
    assert instantanea(args.inbox.parent) == antes


def test_cambio_extractor_exige_coleccion_nueva(sistema, monkeypatch):
    import ingest.offline.intake as modulo

    args, _, fabrica = sistema
    crear_pdf(args.inbox / "fallo.pdf")
    assert ejecutar(sistema) == 0
    configuracion_original = modulo.configuration

    def nueva(*a, **k):
        return {**configuracion_original(*a, **k), "extractor": "version_nueva"}

    monkeypatch.setattr(modulo, "configuration", nueva)
    args.state = args.inbox.parent / "estado_nuevo"
    with pytest.raises(ConfiguracionInvalida, match="versión"):
        Intake(args, fabrica_publicador=fabrica).run()


def test_error_al_iterar_pdf_es_rechazo(sistema, monkeypatch):
    from ingest.offline.intake_worker import analizar

    class PdfConError:
        needs_pass = is_encrypted = is_repaired = False
        page_count = 1

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            raise RuntimeError("Árbol de páginas dañado")

    monkeypatch.setattr(fitz, "open", lambda *a: PdfConError())
    resultado = analizar({"pdf": "sin_abrir.pdf", "destinos": cargar_destinos()})
    assert "iterar" in resultado["rechazo"]


def test_segundo_proceso_no_adquiere_el_bloqueo(tmp_path):
    raiz = Path(__file__).resolve().parents[2]
    script = "from ingest.offline.storage import writer_lock; import sys;\nwith writer_lock(sys.argv[1]): pass"
    with writer_lock(tmp_path):
        proceso = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)], cwd=raiz, capture_output=True
        )
        assert proceso.returncode != 0
        assert b"escritor" in proceso.stderr
    with writer_lock(tmp_path):
        pass


def test_ocr_de_baja_confianza_a_revision(sistema):
    args, _, _ = sistema
    pdf = crear_pdf(args.inbox / "escaneado.pdf", "")
    doc_id = sha256_file(pdf)
    ocr = args.cache / "ocr" / f"{doc_id}-0-{EXTRACTOR_VERSION}.txt"
    ocr.parent.mkdir(parents=True)
    ocr.write_text(TEXTO, encoding="utf-8")
    ocr.with_suffix(".confidence.json").write_text("80.0", encoding="utf-8")
    assert ejecutar(sistema) == 0
    assert fichas(sistema)[0]["decision"] == "revision_humana"
    assert not args.raw_root.exists()


def test_lectura_fallida_no_detiene_los_demas(sistema, monkeypatch):
    import ingest.offline.intake as modulo

    args, _, _ = sistema
    crear_pdf(args.inbox / "a.pdf")
    crear_pdf(args.inbox / "b.pdf", NORMA)
    original = modulo.sha256_file

    def lectura_fallida(ruta):
        if ruta.name == "a.pdf":
            raise PermissionError("Entrada ilegible")
        return original(ruta)

    monkeypatch.setattr(modulo, "sha256_file", lectura_fallida)
    assert ejecutar(sistema) == 2
    assert fichas(sistema)[0]["estado"] == "publicado"
    eventos = [
        json.loads(linea)
        for linea in (args.state / "intake.log.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        e["estado"] == "error_documento" and e["rutas"]["inbox"].endswith("a.pdf") for e in eventos
    )


def test_clasificacion_por_encabezado_propio_de_la_norma():
    # Regresión E2E: una sentencia con una línea de cuerpo «Ley 472 de 1998 contra
    # la DIMAR» quedaba como categoría dudosa.
    sentencia = (
        "TRIBUNAL ADMINISTRATIVO DEL MAGDALENA\nMagistrada sustanciadora: X\n"
        "establecido en el artículo 144 del CPACA y en la\n"
        "Ley 472 de 1998 contra la DIMAR, en la que solicitaron\n"
    )
    resultado = clasificar({"original": sentencia, "raw_pages": [sentencia]})
    assert resultado == {
        "categoria": "jurisprudencia",
        "confianza": 0.95,
        "origen": "reglas_encabezado",
    }
    norma = "DECRETO NÚMERO 1766 DE 2013\n(16 de agosto de 2013)\nDECRETA:\nArtículo 1. Objeto.\n"
    assert clasificar({"original": norma, "raw_pages": [norma]})["categoria"] == "normativa"
    fragmento = "Artículo 29. Las personas que pretendan realizar labores de extracción.\n"
    assert clasificar({"original": fragmento, "raw_pages": [fragmento]})["confianza"] == 0.0
