"""Entrada autónoma local: decisiones auditables, preparación y reversión por documento."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

from ..offline_embeddings import (
    FakeBatchEmbeddings,
    OllamaBatchEmbeddings,
    validar_url_ollama,
    validate_vector,
)
from .extract import sha256_file
from .intake_safety import (
    ConfiguracionInvalida,
    cargar_destinos,
    copiar_raw,
    nombre_seguro,
    validar_destino,
    validar_raw,
)
from .layers import canonical, signature
from .pipeline import configuration
from .policy import PUBLICABLES, cargar_politica, decidir
from .publish import ChromaPublisher
from .storage import atomic_bytes, guard_output, input_scope, writer_lock


def agregar_comandos(comandos):
    intake = comandos.add_parser("intake", help="Procesar documentos PDF sin LLM")
    retiro = comandos.add_parser("retire", help="Retirar un documento conservando su ficha")
    retiro.add_argument("doc_id")
    modo = intake.add_mutually_exclusive_group()
    modo.add_argument("--once", action="store_true", help="Ejecutar una corrida (predeterminado)")
    modo.add_argument("--watch", action="store_true", help="Repetir hasta Ctrl+C")
    intake.add_argument("--intervalo", type=int, default=30)
    intake.add_argument("--dry-run", action="store_true", help="Decidir sin efectos persistentes")
    for comando in (intake, retiro):
        comando.add_argument("--inbox", type=Path, default=Path("data/inbox"))
        comando.add_argument("--raw-root", type=Path, default=Path("data/documents/raw"))
        comando.add_argument("--policy", type=Path)
        comando.add_argument("--destinos", type=Path)
        comando.add_argument("--host", default="127.0.0.1")
        # También se aceptan las opciones globales detrás del subcomando.
        for nombre, tipo in (
            ("collection", str),
            ("layers-root", Path),
            ("cache", Path),
            ("state", Path),
            ("ollama", str),
            ("port", int),
            ("batch-size", int),
            ("chunker", str),
            ("token-budget", int),
        ):
            comando.add_argument("--" + nombre, type=tipo, default=argparse.SUPPRESS)
        for nombre in ("fake-embeddings", "allow-remote-ollama"):
            comando.add_argument("--" + nombre, action="store_true", default=argparse.SUPPRESS)
        comando.add_argument(
            "--from-stage",
            choices=["bronze", "silver", "gold", "embeddings"],
            default=argparse.SUPPRESS,
        )


def fecha():
    return dt.datetime.now(dt.UTC).isoformat()


def leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


@contextmanager
def medir_fase(ficha, nombre, accion):
    inicio = time.monotonic()
    fase = {"accion": accion, "estado": "completada"}
    try:
        yield
    except BaseException:
        fase["estado"] = "error"
        raise
    finally:
        fase["segundos"] = time.monotonic() - inicio
        ficha["tiempos"][nombre] = fase["segundos"]
        ficha.setdefault("fases", {})[nombre] = fase


class Intake:
    """La fábrica inyectable permite Chroma en memoria sin habilitar hosts remotos."""

    def __init__(self, args, *, fabrica_publicador=ChromaPublisher, fabrica_embeddings=None):
        self.args = args
        try:
            self.destinos = cargar_destinos(args.destinos)
            validar_destino(
                args.collection,
                args.host,
                self.destinos,
                ficticios=args.fake_embeddings,
                port=args.port,
            )
            self.politica = cargar_politica(args.policy)
            for seccion in ("rechazo", "revision", "advertencia"):
                for clave, valor in self.politica[seccion].items():
                    if clave.startswith("identidad_"):
                        if not isinstance(valor, bool):
                            raise ValueError(f"La política exige booleano: {clave}")
                    elif (
                        isinstance(valor, bool)
                        or not isinstance(valor, (int, float))
                        or not math.isfinite(valor)
                        or valor < 0
                    ):
                        raise ValueError(f"Umbral de política inválido: {clave}")
            validar_url_ollama(args.ollama, args.allow_remote_ollama)
            if getattr(args, "intervalo", 1) <= 0 or args.batch_size <= 0:
                raise ValueError("intervalo y batch-size deben ser positivos")
            self.config = configuration(args.chunker, args.token_budget)
            if args.chunker not in {"legacy", "structure"} or args.token_budget < 128:
                raise ValueError("Chunker inválido o token-budget menor de 128")
            if args.fake_embeddings:
                self.config.update(model="bench_hash", digest="bench-sha256-768-1")
            self.inbox = args.inbox.resolve()
            self.state = guard_output(args.state or Path(".offline") / args.collection, self.inbox)
            self.capas = guard_output(args.layers_root, self.inbox)
            self.cache = guard_output(args.cache, self.inbox)
            self.raw = validar_raw(args.raw_root, self.inbox)
            # Validación de rutas sin crear directorios ni leer el inbox.
            if self.raw.is_relative_to(self.inbox) or self.inbox.is_relative_to(self.raw):
                raise ValueError("raw-root e inbox deben ser independientes")
            for indice, salida in enumerate((self.state, self.capas, self.cache, self.raw)):
                # No seguir enlaces al clonar el estado durante una simulación.
                if salida.exists() and any(p.is_symlink() for p in salida.rglob("*")):
                    raise ValueError("Las raíces de salida no admiten enlaces simbólicos")
                for otra in (self.state, self.capas, self.cache, self.raw)[indice + 1 :]:
                    if salida.is_relative_to(otra) or otra.is_relative_to(salida):
                        raise ValueError(
                            "Estado, capas, caché y raw requieren raíces independientes"
                        )
            if len(str(self.raw / nombre_seguro("0" * 64))) >= 240:
                raise ValueError("raw-root demasiado largo: ruta total debe ser menor de 240")
            self.gancho = self.destinos.get("gancho_notificacion")
            if self.gancho:
                self.gancho = guard_output(self.gancho, self.inbox)
                if self.gancho.exists() and not self.gancho.is_file():
                    raise ValueError("El gancho debe ser un archivo JSONL")
        except Exception as exc:
            raise ConfiguracionInvalida(str(exc)) from exc
        # Incluye versiones de extractor/chunker: una versión nueva exige colección nueva.
        self.hash = signature(self.config)
        self.fabrica_publicador = fabrica_publicador
        self.fabrica_embeddings = fabrica_embeddings
        self.publicadores = None
        self.embedder = None
        self.pila = None

    def _publicadores(self):
        if self.publicadores is None:
            vivos = []
            with ExitStack() as bloqueos:
                for nombre in (self.args.collection, self.args.collection + "__staging"):
                    try:
                        publicador = self.fabrica_publicador(
                            nombre,
                            self.hash,
                            self.args.port,
                            fake_embeddings=self.args.fake_embeddings,
                        )
                    except ValueError as exc:
                        raise ConfiguracionInvalida(str(exc)) from exc
                    bloqueos.enter_context(publicador.publish_phase())
                    vivos.append(publicador)
                self.pila.enter_context(bloqueos.pop_all())
            self.publicadores = vivos
        return self.publicadores

    def _embeddings(self):
        if self.embedder is None:
            if self.fabrica_embeddings:
                self.embedder = self.fabrica_embeddings(self.cache)
            elif self.args.fake_embeddings:
                self.embedder = FakeBatchEmbeddings(self.cache / "bench_embeddings.sqlite")
            else:
                self.embedder = OllamaBatchEmbeddings(
                    self.cache / "embeddings.sqlite",
                    self.args.ollama,
                    self.args.allow_remote_ollama,
                    self.args.batch_size,
                )
            self.pila.callback(self.embedder.close)
        if (
            self.embedder.digest != self.config["digest"]
            or self.embedder.dimension != 768
            or self.embedder.model != self.config["model"]
        ):
            raise ValueError(
                "Modelo/digest/dimensión de embeddings no coincide con la configuración"
            )
        return self.embedder

    def _ficha(self, doc_id):
        return guard_output(self.state / "intake" / (doc_id + ".json"))

    def _guardar(self, ficha):
        ficha["fecha"] = fecha()
        atomic_bytes(self._ficha(ficha["doc_id"]), canonical(ficha))

    def _evento(self, ficha):
        evento = {
            k: ficha.get(k)
            for k in (
                "doc_id",
                "estado",
                "decision",
                "motivos",
                "avisos",
                "tiempos",
                "fases",
                "coleccion",
                "rutas",
            )
        }
        evento.update(fecha=fecha(), llm_api_calls=0)
        for ruta in (self.state / "intake.log.jsonl", self.gancho):
            if ruta:
                ruta = guard_output(ruta, self.inbox)
                ruta.parent.mkdir(parents=True, exist_ok=True)
                with ruta.open("a", encoding="utf-8") as salida:
                    salida.write(json.dumps(evento, ensure_ascii=False, allow_nan=False) + "\n")

    def _manual(self, archivo, doc_id):
        lateral = archivo.with_name(archivo.name + ".meta.json")
        if lateral.exists():
            if lateral.is_symlink() or not lateral.resolve().is_relative_to(self.inbox):
                raise ValueError("Archivo lateral fuera del inbox")
            datos = leer_json(lateral)
            categoria = datos.get("categoria")
            if categoria not in {"jurisprudencia", "normativa"}:
                raise ValueError("Categoría manual inválida en archivo lateral")
            return categoria
        tabla = self.inbox / "metadata_intake.csv"
        if tabla.exists():
            if tabla.is_symlink():
                raise ValueError("metadata_intake.csv no puede ser un enlace")
            with tabla.open(encoding="utf-8-sig", newline="") as entrada:
                filas = [
                    fila
                    for fila in csv.DictReader(entrada)
                    if fila.get("hash") == doc_id or fila.get("nombre") == archivo.name
                ]
            categorias = {fila.get("categoria") for fila in filas}
            if categorias and (
                len(categorias) != 1 or not categorias <= {"jurisprudencia", "normativa"}
            ):
                raise ValueError("Categorías manuales inválidas o contradictorias en CSV")
            return next(iter(categorias), None)
        return None

    def _analizar(self, archivo, doc_id, categoria):
        # Una instantánea por hash evita TOCTOU y hace PDF la extensión interna.
        with tempfile.TemporaryDirectory(prefix="intake-", dir=self.cache) as temporal:
            temporal = Path(temporal)
            pdf = temporal / nombre_seguro(doc_id)
            shutil.copyfile(archivo, pdf)
            if sha256_file(pdf) != doc_id:
                raise ValueError("La entrada cambió durante el procesamiento")
            solicitud = {
                "pdf": str(pdf),
                "doc_id": doc_id,
                "inbox": str(self.inbox),
                "capas": str(self.capas),
                "db": str(self.state / "intake_layers.sqlite"),
                "cache": str(self.cache),
                "config": self.config,
                "categoria": categoria,
                "destinos": self.destinos,
                "desde": self.args.from_stage,
                "resultado": str(temporal / "resultado.json"),
            }
            ruta = temporal / "solicitud.json"
            atomic_bytes(ruta, canonical(solicitud))
            try:
                proceso = subprocess.run(
                    [sys.executable, "-m", "ingest.offline.intake_worker", str(ruta)],
                    cwd=Path(__file__).resolve().parents[2],
                    capture_output=True,
                    timeout=self.destinos["tiempo_maximo_documento_segundos"],
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Tiempo límite por documento agotado") from exc
            if proceso.returncode or not Path(solicitud["resultado"]).exists():
                raise RuntimeError("El subproceso de extracción falló (posible límite de memoria)")
            resultado = leer_json(solicitud["resultado"])
            if "error" in resultado:
                raise RuntimeError(resultado["error"])
            return resultado

    def _verificar(self, publicador, doc_id, chunks, vectores=None):
        coleccion = publicador.collection
        ids = coleccion.get(where={"doc_id": doc_id}, include=[])["ids"]
        esperados = [c["id"] for c in chunks]
        if len(ids) != len(esperados) or set(ids) != set(esperados):
            raise RuntimeError("No coinciden conteo e ids esperados del documento")
        if vectores is not None:
            canario = coleccion.query(
                query_embeddings=[vectores[0]], n_results=1, where={"doc_id": doc_id}, include=[]
            )
            if not canario["ids"] or canario["ids"][0] != [esperados[0]]:
                raise RuntimeError("Consulta canario fallida: el chunk propio no aparece primero")

    def _revertir(self, doc_id):
        errores = []
        for publicador in self._publicadores():
            try:
                publicador.delete_document(doc_id)
                self._verificar(publicador, doc_id, [])
            except Exception as exc:
                errores.append(str(exc))
        if errores:
            raise RuntimeError("Reversión incompleta; reintentar: " + "; ".join(errores))

    def _publicar(self, ficha):
        doc_id, chunks = ficha["doc_id"], ficha["chunks"]
        ficha["estado"] = "publicando"
        ficha["publicacion_pendiente"] = True
        self._guardar(ficha)  # Sobrevive a interrupciones entre preparación y viva.
        try:
            with medir_fase(
                ficha, "embeddings", "Validar modelo y obtener vectores por caché/lotes"
            ):
                embedder = self._embeddings()
                antes = embedder.new_embeddings
                vectores = embedder.embed([c["document"] for c in chunks])
                if len(vectores) != len(chunks) or not chunks:
                    raise ValueError("Lote de embeddings vacío o incompleto")
                for vector in vectores:
                    validate_vector(vector)
                ficha["embeddings"] = {
                    "nuevos": embedder.new_embeddings - antes,
                    "total": len(vectores),
                    "digest": embedder.digest,
                    "dimension": 768,
                }
            viva, preparacion = self._publicadores()
            # Preparación limpia por documento: un HNSW con muchos borrados dejó de
            # encontrar el vector propio del canario (prueba E2E).
            preparacion.recreate_staging()
            for publicador, fase in ((preparacion, "preparacion"), (viva, "publicacion")):
                with medir_fase(ficha, fase, "Upsert por doc_id, conteos, ids y consulta canario"):
                    conteo = publicador.collection.count()
                    anteriores = len(
                        publicador.collection.get(where={"doc_id": doc_id}, include=[])["ids"]
                    )
                    publicador.upsert_document(doc_id, chunks, vectores)
                    self._verificar(publicador, doc_id, chunks, vectores)
                    if publicador.collection.count() != conteo - anteriores + len(chunks):
                        raise RuntimeError("Conteo total de colección inesperado")
            with medir_fase(
                ficha, "limpieza_preparacion", "Eliminar preparación y verificar vaciado"
            ):
                preparacion.delete_document(doc_id)
                self._verificar(preparacion, doc_id, [])
            ficha["estado"] = "publicado"
            ficha["publicacion_pendiente"] = False
        except ConfiguracionInvalida:
            raise
        except Exception as exc:
            ficha["estado"] = "error_publicacion"
            ficha["motivos"].append(f"Publicación fallida: {exc}")
            try:
                with medir_fase(ficha, "reversion", "Borrar por doc_id en viva y preparación"):
                    self._revertir(doc_id)
                ficha["publicacion_pendiente"] = False
            except Exception as reversion:
                ficha["motivos"].append(str(reversion))

    def _procesar(self, archivo, anteriores, seco):
        inicio = time.monotonic()
        doc_id = sha256_file(archivo)
        ficha = {
            "doc_id": doc_id,
            "hash": doc_id,
            "config_hash": self.hash,
            "configuracion": self.config,
            "coleccion": self.args.collection,
            "estado": "procesando",
            "decision": None,
            "motivos": [],
            "avisos": [],
            "senales": {},
            "metricas": {},
            "tiempos": {},
            "fases": {},
            "chunks": [],
            "embeddings": {},
            "rutas": {"inbox": str(archivo), "capas": str(self.capas), "raw": None},
        }
        try:
            anterior = anteriores.get(doc_id)
            if anterior and (
                anterior.get("accion_pendiente") == "retirar"
                or (anterior["estado"] == "retirado" and not self.args.from_stage)
            ):
                return {
                    **anterior,
                    "resultado": "retiro pendiente"
                    if anterior.get("accion_pendiente")
                    else "sin cambios",
                    "tiempos": {"total": time.monotonic() - inicio},
                }
            manual = self._manual(archivo, doc_id)
            huella = signature([self.config, self.politica, self.destinos, manual])
            ficha["huella_configuracion"] = huella
            if anterior and anterior.get("coleccion") != self.args.collection:
                raise ValueError("Estado de otra colección; utiliza un estado nuevo")
            if (
                anterior
                and anterior.get("huella_configuracion") == huella
                and not self.args.from_stage
            ):
                if anterior["estado"] in {"publicado", "retirado", "rechazado", "revision_humana"}:
                    if anterior["estado"] == "publicado" and not seco:
                        viva, preparacion = self._publicadores()
                        try:
                            self._verificar(viva, doc_id, anterior["chunks"])
                            self._verificar(preparacion, doc_id, [])
                        except RuntimeError:
                            pass  # Reconciliar ids; no declarar éxito con huérfanos.
                        else:
                            return {
                                **anterior,
                                "resultado": "sin cambios",
                                "tiempos": {"total": time.monotonic() - inicio},
                            }
                    else:
                        return {
                            **anterior,
                            "resultado": "sin cambios",
                            "tiempos": {"total": time.monotonic() - inicio},
                        }
            if (
                anterior
                and (
                    anterior["estado"] in {"publicando", "error_publicacion", "publicado"}
                    or anterior.get("publicacion_pendiente")
                )
                and not seco
            ):
                ficha["publicacion_pendiente"] = True
                self._revertir(doc_id)
                ficha["publicacion_pendiente"] = False
            if archivo.stat().st_size > self.destinos["tamano_maximo_bytes"]:
                ficha.update(
                    decision="rechazado", motivos=["PDF desmesurado: supera tamaño máximo"]
                )
            else:
                with archivo.open("rb") as entrada:
                    # Como los lectores PDF, se admite la firma en el primer KiB: dos
                    # PDF reales del corpus empiezan con «\t\n» antes de %PDF-.
                    firma = entrada.read(1024)
                    entrada.seek(max(0, archivo.stat().st_size - 2048))
                    final = entrada.read()
                if b"%PDF-" not in firma:
                    ficha.update(
                        decision="rechazado", motivos=["Firma inválida: no es un PDF (%PDF-)"]
                    )
                elif b"%%EOF" not in final:
                    ficha.update(
                        decision="rechazado", motivos=["PDF truncado: falta marcador final %%EOF"]
                    )
                else:
                    with medir_fase(
                        ficha,
                        "analisis_aislado",
                        "Validar PDF y generar capas en subproceso limitado",
                    ):
                        resultado = self._analizar(archivo, doc_id, manual)
                    if "rechazo" in resultado:
                        ficha.update(decision="rechazado", motivos=[resultado["rechazo"]])
                    else:
                        ficha["tiempos"].update(resultado.pop("tiempos"))
                        ficha["fases"].update(resultado.pop("fases"))
                        ficha.update(resultado)
                        inicio_politica = time.monotonic()
                        cuasi = next(
                            (
                                otro_id
                                for otro_id, otra in sorted(anteriores.items())
                                if otro_id != doc_id
                                and otra.get("estado") == "publicado"
                                and otra.get("coleccion") == self.args.collection
                                and (int(otra["simhash"]) ^ resultado["simhash"]).bit_count()
                                <= self.destinos["simhash_umbral"]
                            ),
                            None,
                        )
                        decision, motivos, avisos = decidir(
                            resultado["senales"], self.politica, cuasi_duplicado_de=cuasi
                        )
                        if cuasi:
                            motivos.append(f"posible versión nueva de {cuasi}")
                        if resultado["clasificacion"]["confianza"] == 0:
                            decision = "revision_humana" if decision != "rechazado" else decision
                            motivos.append("categoría dudosa")
                        ficha.update(decision=decision, motivos=motivos, avisos=avisos)
                        segundos = time.monotonic() - inicio_politica
                        ficha["tiempos"]["politica"] = segundos
                        ficha["fases"]["politica"] = {
                            "accion": "Aplicar política calibrada, categoría y SimHash",
                            "estado": "completada",
                            "segundos": segundos,
                        }
            ficha["estado"] = ficha["decision"]
            if ficha["decision"] in PUBLICABLES and not seco:
                with medir_fase(
                    ficha, "copia_raw", "Copiar documento publicable con nombre SHA-256"
                ):
                    ficha["rutas"]["raw"] = str(copiar_raw(archivo, self.raw, doc_id, self.inbox))
                self._publicar(ficha)
        except ConfiguracionInvalida:
            raise
        except Exception as exc:
            ficha["estado"] = (
                "error_publicacion" if ficha.get("publicacion_pendiente") else "error_documento"
            )
            ficha["motivos"].append(f"{type(exc).__name__}: {exc}")
        ficha["tiempos"]["total"] = time.monotonic() - inicio
        if "validacion" not in ficha["tiempos"]:
            ficha["tiempos"]["validacion"] = ficha["tiempos"]["total"]
        ficha["fases"]["validacion"] = {
            "accion": "Comprobar firma, tamaño, integridad, cifrado y páginas",
            "estado": ficha["decision"] or "error",
            "segundos": ficha["tiempos"]["validacion"],
        }
        if not seco:
            self._guardar(ficha)
        return ficha

    def _informes(self, fichas):
        filas = [
            "# Corrida de entrada autónoma",
            "",
            f"Fecha UTC: {fecha()}. Llamadas LLM: 0.",
            "",
            "| Documento | Decisión | Estado | Segundos | Motivos |",
            "|---|---|---|---:|---|",
        ]
        for ficha in fichas:
            motivo = "; ".join(ficha["motivos"]).replace("|", "/").replace("\n", " ")
            filas.append(
                f"| {ficha['doc_id']} | {ficha['decision']} | {ficha.get('resultado', ficha['estado'])} | {ficha['tiempos']['total']:.3f} | {motivo} |"
            )
        atomic_bytes(self.state / "intake_report.md", ("\n".join(filas) + "\n").encode())
        cola = self.state / "review_queue.csv"
        acumulado = {}
        if cola.exists():
            with cola.open(encoding="utf-8", newline="") as entrada:
                acumulado = {fila["doc_id"]: fila for fila in csv.DictReader(entrada)}
        for ficha in fichas:
            if ficha["decision"] == "revision_humana":
                acumulado[ficha["doc_id"]] = {
                    "doc_id": ficha["doc_id"],
                    "nombre": Path(ficha["rutas"]["inbox"]).name,
                    "motivos": "; ".join(ficha["motivos"]),
                    "estado": ficha["estado"],
                }
            elif ficha["doc_id"] in acumulado:
                acumulado[ficha["doc_id"]]["estado"] = ficha["estado"]
        salida = io.StringIO(newline="")
        escritor = csv.DictWriter(salida, fieldnames=["doc_id", "nombre", "motivos", "estado"])
        escritor.writeheader()
        escritor.writerows(acumulado[k] for k in sorted(acumulado))
        atomic_bytes(cola, salida.getvalue().encode())

    def run(self):
        seco = getattr(self.args, "dry_run", False)
        originales = self.state, self.capas, self.cache
        try:
            with ExitStack() as pila:
                self.pila = pila
                if seco:
                    temporal = Path(
                        pila.enter_context(tempfile.TemporaryDirectory(prefix="intake-seco-"))
                    )
                    self.state, self.capas, self.cache = (
                        temporal / nombre for nombre in ("estado", "capas", "cache")
                    )
                    for origen, destino in zip(
                        originales, (self.state, self.capas, self.cache), strict=True
                    ):
                        if origen.exists():
                            shutil.copytree(origen, destino, symlinks=True)
                else:
                    pila.enter_context(input_scope(self.inbox))
                    pila.enter_context(writer_lock(self.state, self.capas, self.cache))
                self.state.mkdir(parents=True, exist_ok=True)
                self.cache.mkdir(parents=True, exist_ok=True)
                ajustes = self.state / "intake_config.json"
                if ajustes.exists() and leer_json(ajustes) != {
                    "coleccion": self.args.collection,
                    "config_hash": self.hash,
                }:
                    raise ConfiguracionInvalida(
                        "Estado de otra versión/colección; utiliza estado y colección nuevos"
                    )
                if not seco:
                    atomic_bytes(
                        ajustes,
                        canonical({"coleccion": self.args.collection, "config_hash": self.hash}),
                    )
                anteriores = {p.stem: leer_json(p) for p in (self.state / "intake").glob("*.json")}
                if self.args.command == "retire":
                    return self._retirar(anteriores)
                # Un retiro interrumpido conserva la intención del operador.
                for ficha in anteriores.values():
                    if ficha.get("accion_pendiente") == "retirar" and not seco:
                        self._terminar_retiro(ficha)
                        self._guardar(ficha)
                if not self.inbox.is_dir():
                    raise ConfiguracionInvalida("El inbox debe ser un directorio existente")
                fichas = []
                for archivo in sorted(self.inbox.iterdir()):
                    if (
                        archivo.name == "metadata_intake.csv"
                        or archivo.name.endswith(".meta.json")
                        or not archivo.is_file()
                    ):
                        continue
                    if archivo.is_symlink():
                        raise ConfiguracionInvalida("El inbox no admite enlaces simbólicos")
                    try:
                        ficha = self._procesar(archivo, anteriores, seco)
                    except OSError as exc:
                        # Sin poder leer bytes no existe una identidad fiable.
                        # Dejar evidencia en la corrida y continuar con los demás.
                        ficha = {
                            "doc_id": None,
                            "decision": None,
                            "estado": "error_documento",
                            "motivos": [f"No se pudo leer la entrada: {type(exc).__name__}"],
                            "avisos": [],
                            "tiempos": {"total": 0.0},
                            "coleccion": self.args.collection,
                            "rutas": {"inbox": str(archivo)},
                        }
                    fichas.append(ficha)
                    if ficha["doc_id"]:
                        anteriores[ficha["doc_id"]] = ficha
                    if not seco:
                        self._evento(ficha)
                    print(
                        json.dumps(
                            {
                                k: ficha.get(k)
                                for k in (
                                    "doc_id",
                                    "decision",
                                    "estado",
                                    "resultado",
                                    "motivos",
                                    "avisos",
                                    "tiempos",
                                    "fases",
                                )
                            },
                            ensure_ascii=False,
                        )
                    )
                if not seco:
                    self._informes(fichas)
                return (
                    2
                    if any(
                        f["estado"].startswith("error") for f in fichas + list(anteriores.values())
                    )
                    else 0
                )
        finally:
            self.state, self.capas, self.cache = originales
            self.publicadores = self.embedder = self.pila = None

    def _retirar(self, anteriores):
        doc_id = self.args.doc_id
        nombre_seguro(doc_id)
        if doc_id not in anteriores:
            raise ConfiguracionInvalida("No existe ficha para ese doc_id")
        ficha = anteriores[doc_id]
        ficha.update(estado="retirando", accion_pendiente="retirar")
        self._guardar(ficha)
        self._terminar_retiro(ficha)
        self._guardar(ficha)
        self._evento(ficha)
        self._informes([ficha])
        print(json.dumps({"doc_id": doc_id, "estado": ficha["estado"]}, ensure_ascii=False))
        return 2 if ficha["estado"] == "error_publicacion" else 0

    def _terminar_retiro(self, ficha):
        try:
            self._revertir(ficha["doc_id"])
            ficha["estado"] = "retirado"
            ficha.pop("accion_pendiente", None)
            ficha["publicacion_pendiente"] = False
        except ConfiguracionInvalida:
            raise
        except Exception as exc:
            ficha["estado"] = "error_publicacion"
            ficha["motivos"].append(f"Retiro incompleto: {exc}")


def ejecutar(args):
    codigo = 0
    try:
        intake = Intake(args)
        while True:
            codigo = max(codigo, intake.run())
            if not getattr(args, "watch", False):
                return codigo
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("Observación detenida por el operador")
        return codigo
    except (ConfiguracionInvalida, ValueError) as exc:
        print(f"Configuración inválida o destino protegido: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Error de entrada autónoma: {exc}", file=sys.stderr)
        return 2
