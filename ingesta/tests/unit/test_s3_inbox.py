"""Buzón S3 en memoria, sin boto3 real, red ni LLM."""

from __future__ import annotations

import errno
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_intake import crear_pdf
from test_intake import sistema as sistema

from ingest.offline.__main__ import main
from ingest.offline.intake import Intake
from ingest.offline.intake_safety import ConfiguracionInvalida
from ingest.offline.layers import canonical
from ingest.offline.s3_inbox import S3Inbox, analizar_uri, ejecutar, huella_origen


class ErrorS3(Exception):
    def __init__(self, codigo):
        self.response = {"Error": {"Code": codigo, "Message": "MENSAJE_NO_REGISTRABLE"}}


class S3Falso:
    def __init__(self):
        self.objetos = {}
        self.llamadas = []
        self.pagina = 1
        self.fallo_borrado = False
        self.corromper_copia = False
        self.incluir_fuera = False

    def _llamada(self, operacion, opciones):
        assert opciones["Bucket"] == "bucket-pruebas"
        self.llamadas.append((operacion, opciones.copy()))

    def sembrar(self, clave, cuerpo, metadata=None):
        self.objetos[clave] = {
            "Body": cuerpo,
            "ContentLength": len(cuerpo),
            "ETag": '"' + hashlib.sha256(cuerpo).hexdigest() + '"',
            "Metadata": metadata or {},
        }

    def list_objects_v2(self, **opciones):
        self._llamada("listar", opciones)
        claves = sorted(
            k for k in self.objetos if self.incluir_fuera or k.startswith(opciones["Prefix"])
        )
        inicio = int(opciones.get("ContinuationToken", "0"))
        fin = inicio + self.pagina
        return {
            "Contents": [
                {"Key": k, "Size": self.objetos[k]["ContentLength"]} for k in claves[inicio:fin]
            ],
            "IsTruncated": fin < len(claves),
            "NextContinuationToken": str(fin),
        }

    def head_object(self, **opciones):
        self._llamada("cabecera", opciones)
        if opciones["Key"] not in self.objetos:
            raise ErrorS3("404")
        return {k: v for k, v in self.objetos[opciones["Key"]].items() if k != "Body"}

    def get_object(self, **opciones):
        self._llamada("descargar", opciones)
        objeto = self.objetos[opciones["Key"]]
        assert opciones.get("IfMatch", objeto["ETag"]) == objeto["ETag"]
        return {**objeto, "Body": io.BytesIO(objeto["Body"])}

    def download_file(self, Bucket, Key, Filename):
        Path(Filename).write_bytes(self.get_object(Bucket=Bucket, Key=Key)["Body"].read())

    def put_object(self, **opciones):
        self._llamada("subir", opciones)
        self.sembrar(opciones["Key"], opciones["Body"], opciones.get("Metadata"))

    def upload_file(self, Filename, Bucket, Key):
        self.put_object(Bucket=Bucket, Key=Key, Body=Path(Filename).read_bytes())

    def copy_object(self, **opciones):
        self._llamada("copiar", opciones)
        assert opciones["CopySource"]["Bucket"] == opciones["Bucket"]
        original = self.objetos[opciones["CopySource"]["Key"]]
        assert opciones["CopySourceIfMatch"] == original["ETag"]
        self.sembrar(opciones["Key"], original["Body"], opciones.get("Metadata"))
        etag = self.objetos[opciones["Key"]]["ETag"]
        if self.corromper_copia:
            self.objetos[opciones["Key"]]["ContentLength"] += 1
        return {"CopyObjectResult": {"ETag": etag}}

    def delete_object(self, **opciones):
        self._llamada("borrar", opciones)
        if self.fallo_borrado:
            self.fallo_borrado = False
            raise ConnectionError("Fallo simulado antes del borrado")
        self.objetos.pop(opciones["Key"], None)


@pytest.fixture
def buzon(sistema):
    args, cliente_chroma, fabrica = sistema
    args.inbox = "s3://bucket-pruebas/inbox/"
    args.watch = False
    s3 = S3Falso()
    adaptador = S3Inbox(args, cliente=s3, fabrica_publicador=fabrica)
    return adaptador, s3, cliente_chroma


def pdf(sistema, texto=None):
    ruta = sistema[0].state.parent / "original.pdf"
    return (crear_pdf(ruta) if texto is None else crear_pdf(ruta, texto)).read_bytes()


def ficha_remota(s3, prefijo):
    clave = next(k for k in s3.objetos if k.startswith(prefijo) and k.endswith("/ficha.json"))
    return json.loads(s3.objetos[clave]["Body"])


def eventos(sistema):
    return [
        json.loads(linea)
        for linea in (sistema[0].state / "intake.log.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


@pytest.mark.parametrize(
    "texto,prefijo,estado",
    [
        (None, "processed/", "publicado"),
        ("Documento sin encabezado. " * 20, "review/", "revision_humana"),
    ],
)
def test_pdf_a_su_destino(buzon, sistema, texto, prefijo, estado):
    adaptador, s3, chroma = buzon
    cuerpo = pdf(sistema, texto)
    s3.sembrar("inbox/subcarpeta/documento con espacios.pdf", cuerpo)
    assert adaptador.run() == 0
    identidad = hashlib.sha256(cuerpo).hexdigest()
    assert set(s3.objetos) == {
        prefijo + identidad + "/" + n for n in ("ficha.json", "motivo.txt", "original.pdf")
    }
    ficha = ficha_remota(s3, prefijo)
    assert ficha["estado"] == estado
    assert ficha["hash"] == identidad
    assert ficha["nombre_original"] == "documento con espacios.pdf"
    assert s3.objetos[prefijo + identidad + "/original.pdf"]["Body"] == cuerpo
    if estado == "publicado":
        assert chroma.get_collection(sistema[0].collection).count() == len(ficha["chunks"])
    assert any(e["estado"] == "s3_movido" and e["llm_api_calls"] == 0 for e in eventos(sistema))
    operaciones = [n for n, _ in s3.llamadas]
    assert operaciones.index("copiar") < operaciones.index("borrar")
    assert "cabecera" in operaciones[operaciones.index("copiar") + 1 : operaciones.index("borrar")]


def test_no_pdf_rechazado_con_motivo(buzon):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/no-es-pdf.txt", b"Esto no es PDF")
    assert adaptador.run() == 0
    assert "inbox/no-es-pdf.txt" not in s3.objetos
    assert ficha_remota(s3, "rejected/")["estado"] == "rechazado"
    motivo = next(v["Body"] for k, v in s3.objetos.items() if k.endswith("/motivo.txt"))
    assert b"no es un PDF" in motivo


def test_desmesurado_sin_descarga(buzon, sistema, monkeypatch):
    import ingest.offline.intake as modulo

    adaptador, s3, _ = buzon
    destinos = modulo.cargar_destinos()
    destinos["tamano_maximo_bytes"] = 4
    monkeypatch.setattr(modulo, "cargar_destinos", lambda *_: destinos)
    s3.sembrar("inbox/grande.pdf", b"0123456789")
    assert adaptador.run() == 0
    assert not any(n == "descargar" for n, _ in s3.llamadas)
    ficha = ficha_remota(s3, "rejected/")
    assert ficha["hash"] is None
    assert ficha["doc_id"].startswith("desmesurado-")
    assert "supera el tamaño máximo" in ficha["motivos"][0]
    assert "inbox/grande.pdf" not in s3.objetos
    assert (sistema[0].state / "intake_config.json").exists()
    assert "rechazado" in (sistema[0].state / "intake_report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("fallar", [False, True])
def test_desmesurado_mayor_de_cinco_gb_se_copia_por_partes(buzon, monkeypatch, fallar):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/gigante.pdf", b"objeto virtual")
    tamano = 5_000_000_001
    s3.objetos["inbox/gigante.pdf"]["ContentLength"] = tamano
    rangos = []
    metadatos = {}

    def crear(**opciones):
        s3._llamada("iniciar_partes", opciones)
        metadatos.update(opciones["Metadata"])
        return {"UploadId": "carga-falsa"}

    def copiar_parte(**opciones):
        s3._llamada("copiar_parte", opciones)
        assert opciones["CopySourceIfMatch"] == s3.objetos["inbox/gigante.pdf"]["ETag"]
        if fallar:
            raise ConnectionError("Copia por partes interrumpida")
        rangos.append(opciones["CopySourceRange"])
        return {"CopyPartResult": {"ETag": f'"parte-{len(rangos)}"'}}

    def completar(**opciones):
        s3._llamada("completar_partes", opciones)
        assert len(opciones["MultipartUpload"]["Parts"]) == len(rangos)
        s3.sembrar(opciones["Key"], b"objeto virtual", metadatos)
        s3.objetos[opciones["Key"]]["ContentLength"] = tamano
        return {"ETag": s3.objetos[opciones["Key"]]["ETag"]}

    monkeypatch.setattr(s3, "create_multipart_upload", crear, raising=False)
    monkeypatch.setattr(s3, "upload_part_copy", copiar_parte, raising=False)
    monkeypatch.setattr(s3, "complete_multipart_upload", completar, raising=False)
    monkeypatch.setattr(
        s3, "abort_multipart_upload", lambda **o: s3._llamada("abortar_partes", o), raising=False
    )
    if fallar:
        with pytest.raises(ConnectionError):
            adaptador.run()
        assert "inbox/gigante.pdf" in s3.objetos
        assert any(n == "abortar_partes" for n, _ in s3.llamadas)
    else:
        assert adaptador.run() == 0
        assert "inbox/gigante.pdf" not in s3.objetos
        assert rangos[0].startswith("bytes=0-")
        assert rangos[-1].endswith(f"-{tamano - 1}")
    assert not any(n in {"descargar", "copiar"} for n, _ in s3.llamadas)


def test_paginacion_carpetas_y_claves_hostiles(buzon, sistema):
    adaptador, s3, _ = buzon
    claves = [
        "inbox/../mal.pdf",
        "inbox/a\x00.pdf",
        "inbox/a\x7f.pdf",
        "inbox/a\\b.pdf",
        "fuera/a.pdf",
        "inbox/carpeta/",
    ]
    for clave in claves:
        s3.sembrar(clave, b"")
    s3.incluir_fuera = True
    s3.sembrar("inbox/valido.txt", b"no pdf")
    assert adaptador.run() == 0
    assert all(k in s3.objetos for k in claves)
    assert "inbox/valido.txt" not in s3.objetos
    assert sum(n == "listar" for n, _ in s3.llamadas) == 7
    assert not any(n == "descargar" and o["Key"] in claves for n, o in s3.llamadas)
    assert sum(e["estado"] == "s3_ignorado" for e in eventos(sistema)) == 5


def test_reanudacion_solo_borra_sin_chroma(buzon, sistema, monkeypatch):
    adaptador, s3, chroma = buzon
    cuerpo = pdf(sistema)
    s3.sembrar("inbox/fallo.pdf", cuerpo)
    s3.fallo_borrado = True
    with pytest.raises(ConnectionError):
        adaptador.run()
    ficha = ficha_remota(s3, "processed/")
    conteo = chroma.get_collection(sistema[0].collection).count()
    assert "inbox/fallo.pdf" in s3.objetos
    s3.llamadas.clear()

    def prohibido(*a, **k):
        pytest.fail("La reanudación no debe ejecutar el intake ni tocar Chroma")

    monkeypatch.setattr(Intake, "run", prohibido)
    assert adaptador.run() == 0
    assert set(n for n, _ in s3.llamadas) == {"listar", "cabecera", "borrar"}
    assert chroma.get_collection(sistema[0].collection).count() == conteo == len(ficha["chunks"])
    assert "inbox/fallo.pdf" not in s3.objetos
    assert eventos(sistema)[-1]["s3"]["resultado"] == "sin cambios"


def test_contenido_duplicado_no_repite_trabajo(buzon, sistema, monkeypatch):
    adaptador, s3, chroma = buzon
    cuerpo = pdf(sistema)
    s3.sembrar("inbox/primero.pdf", cuerpo)
    assert adaptador.run() == 0
    antes = set(s3.objetos)
    conteo = chroma.get_collection(sistema[0].collection).count()

    def prohibido(*a, **k):
        pytest.fail("No deben repetirse análisis ni embeddings")

    monkeypatch.setattr(Intake, "_analizar", prohibido)
    monkeypatch.setattr(Intake, "_embeddings", prohibido)
    s3.sembrar("inbox/otro-nombre.pdf", cuerpo)
    s3.llamadas.clear()
    assert adaptador.run() == 0
    assert set(s3.objetos) == antes
    assert not any(n in {"subir", "copiar"} for n, _ in s3.llamadas)
    assert chroma.get_collection(sistema[0].collection).count() == conteo
    assert eventos(sistema)[-2]["s3"]["resultado"] == "sin cambios"


def test_dry_run_sin_efectos(buzon, sistema):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/normal.pdf", pdf(sistema))
    sistema[0].dry_run = True
    raiz = sistema[0].state.parent
    antes = {p.relative_to(raiz): p.read_bytes() for p in raiz.rglob("*") if p.is_file()}
    assert adaptador.run() == 0
    assert set(s3.objetos) == {"inbox/normal.pdf"}
    assert not any(n in {"subir", "copiar", "borrar"} for n, _ in s3.llamadas)
    assert antes == {p.relative_to(raiz): p.read_bytes() for p in raiz.rglob("*") if p.is_file()}


def test_copia_incorrecta_nunca_borra(buzon):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/original.txt", b"no pdf")
    s3.corromper_copia = True
    with pytest.raises(RuntimeError, match="incompatible"):
        adaptador.run()
    assert "inbox/original.txt" in s3.objetos
    assert not any(n == "borrar" for n, _ in s3.llamadas)


@pytest.mark.parametrize(
    "fase,estado", [("_analizar", "error_documento"), ("_embeddings", "error_publicacion")]
)
def test_error_documento_permanece_en_buzon(buzon, sistema, monkeypatch, fase, estado):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/reintentar.pdf", pdf(sistema))

    def fallar(*a):
        raise RuntimeError("Fallo de extracción simulado")

    monkeypatch.setattr(Intake, fase, fallar)
    assert adaptador.run() == 2
    assert set(s3.objetos) == {"inbox/reintentar.pdf"}
    assert any(e["estado"] == "s3_pendiente" for e in eventos(sistema))
    assert eventos(sistema)[-1]["estado"] == estado


def test_original_sustituido_durante_copia_no_se_borra(buzon, monkeypatch):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/cambiante.txt", b"primera version")
    copiar = s3.copy_object

    def sustituir(**opciones):
        resultado = copiar(**opciones)
        s3.sembrar("inbox/cambiante.txt", b"segunda version")
        return resultado

    monkeypatch.setattr(s3, "copy_object", sustituir)
    with pytest.raises(RuntimeError, match="original S3 cambió"):
        adaptador.run()
    assert s3.objetos["inbox/cambiante.txt"]["Body"] == b"segunda version"
    assert not any(n == "borrar" for n, _ in s3.llamadas)


def test_descarga_interrumpida_es_atomica_y_reintentable(buzon, sistema, monkeypatch):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/interrumpido.pdf", pdf(sistema))
    descargar = s3.get_object

    class CuerpoInterrumpido(io.BytesIO):
        def read(self, *args):
            if self.tell():
                raise ConnectionError("Descarga interrumpida")
            return super().read(20)

    def interrumpir(**opciones):
        respuesta = descargar(**opciones)
        respuesta["Body"] = CuerpoInterrumpido(s3.objetos[opciones["Key"]]["Body"])
        return respuesta

    with monkeypatch.context() as contexto:
        contexto.setattr(s3, "get_object", interrumpir)
        with pytest.raises(ConnectionError):
            adaptador.run()
    assert not list(sistema[0].state.rglob("*.part"))
    assert not list(sistema[0].state.rglob("entrada.pdf"))
    assert set(s3.objetos) == {"inbox/interrumpido.pdf"}
    assert adaptador.run() == 0


def test_reanudacion_rechaza_sha256_del_destino_incompatible(buzon):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/pendiente.txt", b"no pdf")
    s3.fallo_borrado = True
    with pytest.raises(ConnectionError):
        adaptador.run()
    destino = next(k for k in s3.objetos if k.endswith("/original.pdf"))
    s3.objetos[destino]["Metadata"]["sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="SHA-256"):
        adaptador.run()
    assert "inbox/pendiente.txt" in s3.objetos


@pytest.mark.parametrize("codigo", ["ExpiredToken", "AccessDenied"])
def test_autorizacion_sale_y_no_registra_mensajes(buzon, sistema, monkeypatch, capsys, codigo):
    _, s3, _ = buzon

    def fallar(**opciones):
        raise ErrorS3(codigo)

    monkeypatch.setattr(s3, "list_objects_v2", fallar)
    args, _, fabrica = sistema
    args.watch = True
    assert ejecutar(args, cliente=s3, fabrica_publicador=fabrica) == 2
    assert codigo in capsys.readouterr().err
    texto = (args.state / "intake.log.jsonl").read_text(encoding="utf-8")
    assert codigo in texto
    assert "MENSAJE_NO_REGISTRABLE" not in texto


def test_watch_reintenta_red_con_espera_acotada(buzon, sistema, monkeypatch):
    _, s3, _ = buzon
    intentos, esperas = [], []

    def fallar(**opciones):
        intentos.append(1)
        if len(intentos) <= 9:
            raise ConnectionError("Fallo de red")
        raise ErrorS3("AccessDenied")

    monkeypatch.setattr(s3, "list_objects_v2", fallar)
    args, _, fabrica = sistema
    args.watch = True
    assert ejecutar(args, cliente=s3, fabrica_publicador=fabrica, espera=esperas.append) == 2
    assert esperas == [2, 4, 8, 16, 32, 60, 60, 60, 60]


@pytest.mark.parametrize(
    "uri",
    [
        "s3://bucket-pruebas",
        "s3://bucket-pruebas/",
        "s3://bucket-pruebas/inbox",
        "s3://bucket-pruebas/a/../",
        "s3://bucket-pruebas/a/?clave=x",
        "s3://bucket-pruebas/processed/",
        "s3://usuario@bucket-pruebas/inbox/",
    ],
)
def test_uri_exige_bucket_y_prefijo_explicitos(uri):
    with pytest.raises(ConfiguracionInvalida):
        analizar_uri(uri)


def test_cli_conserva_uri_y_carga_adaptador_solo_para_s3(buzon, sistema, monkeypatch):
    import ingest.offline.s3_inbox as modulo

    def ejecutar_falso(args):
        assert args.inbox == "s3://bucket-pruebas/inbox/"
        return 0

    monkeypatch.setattr(modulo, "ejecutar", ejecutar_falso)
    assert (
        main(
            ["intake", "--inbox", sistema[0].inbox, "--collection", sistema[0].collection, "--once"]
        )
        == 0
    )


def test_importar_nucleo_no_carga_boto3():
    script = (
        "import sys; import ingest.offline.intake; "
        "assert 'boto3' not in sys.modules; "
        "assert 'ingest.offline.s3_inbox' not in sys.modules"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2], capture_output=True
    )
    assert resultado.returncode == 0, resultado.stderr.decode(errors="replace")


def test_boto3_sigue_en_dependencias_normales_y_extra_aws():
    import tomllib

    proyecto = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    assert "boto3>=1.34" in proyecto["dependencies"]
    assert "boto3>=1.34" in proyecto["optional-dependencies"]["aws"]


def test_sustitucion_tras_verificar_copia_sin_versionado_conserva_original(
    buzon, sistema, monkeypatch
):
    adaptador, s3, _ = buzon
    clave = "inbox/cambiante.txt"
    s3.sembrar(clave, b"primera")
    verificar = adaptador._destino_valido

    def sustituir(*args):
        copia = verificar(*args)
        if copia:
            s3.sembrar(clave, b"segunda")
        return copia

    monkeypatch.setattr(adaptador, "_destino_valido", sustituir)
    with pytest.raises(RuntimeError, match="original S3 cambió"):
        adaptador.run()
    assert s3.objetos[clave]["Body"] == b"segunda"
    assert not any(n == "borrar" for n, _ in s3.llamadas)
    assert any(e["estado"] == "s3_original_conservado" for e in eventos(sistema))


def test_sustitucion_justo_antes_de_borrar_elimina_solo_version_copiada(buzon, monkeypatch):
    adaptador, s3, _ = buzon
    clave = "inbox/versionada.txt"
    s3.sembrar(clave, b"primera")
    s3.objetos[clave]["VersionId"] = "v1"
    copiar = s3.copy_object

    def copia_version(**opciones):
        assert opciones["CopySource"]["VersionId"] == "v1"
        return copiar(**opciones)

    def borrar_version(**opciones):
        s3._llamada("borrar", opciones)
        # La subida nueva ocurre después de la última verificación.
        s3.sembrar(clave, b"segunda")
        s3.objetos[clave]["VersionId"] = "v2"
        assert opciones["VersionId"] == "v1"

    monkeypatch.setattr(s3, "copy_object", copia_version)
    monkeypatch.setattr(s3, "delete_object", borrar_version)
    assert adaptador.run() == 0
    assert s3.objetos[clave]["VersionId"] == "v2"
    assert s3.objetos[clave]["Body"] == b"segunda"
    assert any(n == "descargar" and o["VersionId"] == "v1" for n, o in s3.llamadas)


def test_reanudacion_regenera_informes_y_cola_de_revision(buzon, sistema):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/revision.pdf", pdf(sistema, "Documento sin encabezado. " * 20))
    s3.fallo_borrado = True
    with pytest.raises(ConnectionError):
        adaptador.run()
    ficha = ficha_remota(s3, "review/")
    for nombre in ("review_queue.csv", "intake_report.md"):
        (sistema[0].state / nombre).unlink(missing_ok=True)
    assert adaptador.run() == 0
    for nombre in ("review_queue.csv", "intake_report.md"):
        assert ficha["doc_id"] in (sistema[0].state / nombre).read_text(encoding="utf-8")


@pytest.mark.parametrize("fase", ["preparacion", "directorio", "descarga"])
def test_error_permanente_aislado_rechaza_y_sigue_con_la_cola(buzon, monkeypatch, fase):
    import ingest.offline.s3_inbox as modulo

    adaptador, s3, _ = buzon
    clave = "inbox/a-error.pdf"
    s3.sembrar(clave, b"primero")
    s3.sembrar("inbox/b-valido.txt", b"segundo")
    identidad_origen = hashlib.sha256(
        canonical([adaptador.bucket, clave, huella_origen(s3.objetos[clave])])
    ).hexdigest()
    if fase == "preparacion":
        nombre = modulo.nombre_visible

        def preparar(valor, identidad):
            if valor == clave:
                raise ValueError("Preparación imposible")
            return nombre(valor, identidad)

        monkeypatch.setattr(modulo, "nombre_visible", preparar)
    elif fase == "directorio":
        crear = Path.mkdir
        identidad = hashlib.sha256(clave.encode("utf-8")).hexdigest()

        def crear_directorio(self, *args, **opciones):
            if self.name == identidad:
                raise OSError(errno.ENAMETOOLONG, "Directorio imposible")
            return crear(self, *args, **opciones)

        monkeypatch.setattr(Path, "mkdir", crear_directorio)
    else:
        descargar = adaptador._descargar

        def descarga(valor, *args):
            if valor == clave:
                raise OSError(errno.ENAMETOOLONG, "Nombre demasiado largo")
            return descargar(valor, *args)

        monkeypatch.setattr(adaptador, "_descargar", descarga)
    assert adaptador.run() == 0
    ficha = json.loads(s3.objetos[f"rejected/{identidad_origen}/ficha.json"]["Body"])
    assert ficha["estado"] == "rechazado"
    assert "descarga" in ficha["motivos"][0]
    assert not any(k.startswith("inbox/") for k in s3.objetos)
    assert sum(k.endswith("/original.pdf") for k in s3.objetos) == 2


@pytest.mark.parametrize("fase", ["preparacion", "descarga"])
def test_rechazos_misma_clave_y_tamano_copian_cada_contenido(buzon, monkeypatch, fase):
    import ingest.offline.s3_inbox as modulo

    adaptador, s3, _ = buzon
    clave = "inbox/error.pdf"

    def fallar(*args):
        raise OSError(errno.ENAMETOOLONG, "Error permanente")

    if fase == "preparacion":
        monkeypatch.setattr(modulo, "nombre_visible", fallar)
    else:
        monkeypatch.setattr(adaptador, "_descargar", fallar)

    borrar = s3.delete_object

    def borrar_con_copia(**opciones):
        cuerpo = s3.objetos[opciones["Key"]]["Body"]
        assert any(
            k.startswith("rejected/") and k.endswith("/original.pdf") and v["Body"] == cuerpo
            for k, v in s3.objetos.items()
        )
        borrar(**opciones)

    monkeypatch.setattr(s3, "delete_object", borrar_con_copia)
    cuerpos = (b"primero", b"segundo")
    assert len(cuerpos[0]) == len(cuerpos[1])
    for cuerpo in cuerpos:
        s3.sembrar(clave, cuerpo)
        assert adaptador.run() == 0
        assert clave not in s3.objetos
    copias = [o["Key"] for n, o in s3.llamadas if n == "copiar"]
    assert len(copias) == len(set(copias)) == 2
    assert {s3.objetos[k]["Body"] for k in copias} == set(cuerpos)
    assert sum(n == "borrar" for n, _ in s3.llamadas) == 2


def test_nombre_s3_de_120_ideogramas_no_bloquea_descarga(buzon):
    adaptador, s3, _ = buzon
    s3.sembrar("inbox/" + "漢" * 120 + ".pdf", b"no pdf")
    assert adaptador.run() == 0
    assert ficha_remota(s3, "rejected/")["estado"] == "rechazado"
