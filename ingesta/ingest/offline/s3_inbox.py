"""Transporte S3 opcional: el intake local conserva todas las decisiones, sin LLM."""

from __future__ import annotations

import copy
import errno
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from .intake import Intake
from .intake_safety import ConfiguracionInvalida, comprobar_worker, nombre_visible
from .layers import canonical
from .storage import atomic_bytes, guard_output, writer_lock

DESTINOS = {"publicado": "processed", "revision_humana": "review", "rechazado": "rejected"}
AUTORIZACION = {"ExpiredToken", "ExpiredTokenException", "AccessDenied", "InvalidAccessKeyId"}


def cliente_predeterminado():
    """Único punto de importación AWS; exclusivamente la cadena estándar del SDK."""
    try:
        import boto3
    except ImportError as exc:
        raise ConfiguracionInvalida(
            "S3 requiere instalar el extra opcional: .[offline,aws]"
        ) from exc
    return boto3.client("s3")


def codigo_error(exc):
    # No registrar mensajes del SDK, solicitudes, cabeceras ni credenciales.
    codigo = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    return codigo if re.fullmatch(r"[A-Za-z0-9]+", str(codigo)) else type(exc).__name__


def transitorio(exc):
    return (
        isinstance(exc, (ConnectionError, TimeoutError))
        or isinstance(exc, OSError)
        and exc.errno in {errno.EAGAIN, errno.EINTR, errno.ETIMEDOUT, errno.ECONNRESET}
        or type(exc).__name__
        in {
            "EndpointConnectionError",
            "ConnectionClosedError",
            "ReadTimeoutError",
            "ConnectTimeoutError",
            "ResponseStreamingError",
            "IncompleteReadError",
            "SSLError",
            "ProxyConnectionError",
        }
        or codigo_error(exc)
        in {
            "SlowDown",
            "RequestTimeout",
            "InternalError",
            "ServiceUnavailable",
            "500",
            "502",
            "503",
            "504",
        }
    )


def clave_segura(clave):
    return (
        isinstance(clave, str)
        and ".." not in clave
        and "\\" not in clave
        and not any(unicodedata.category(c).startswith("C") for c in clave)
    )


def analizar_uri(uri):
    partes = urlsplit(str(uri))
    bucket, prefijo = partes.netloc, partes.path.lstrip("/")
    if (
        partes.scheme != "s3"
        or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
        or ".." in bucket
        or not prefijo
        or not partes.path.startswith("/")
        or partes.path.startswith("//")
        or not prefijo.endswith("/")
        or any(not p for p in prefijo[:-1].split("/"))
        or not clave_segura(prefijo)
        or partes.query
        or partes.fragment
        or any(unicodedata.category(c).startswith("C") for c in str(uri))
    ):
        raise ConfiguracionInvalida("El buzón S3 exige s3://bucket/prefijo/ explícito y seguro")
    # Impedir que los destinos de esta corrida vuelvan a entrar en su propio buzón.
    if prefijo.split("/", 1)[0] in DESTINOS.values():
        raise ConfiguracionInvalida("El prefijo del buzón coincide con un destino S3 reservado")
    return bucket, prefijo


def huella_origen(cabecera):
    return {k: cabecera[k] for k in ("ETag", "ContentLength", "VersionId") if k in cabecera}


def destino_ficha(ficha, identidad):
    if not re.fullmatch(r"[0-9a-f]{64}", identidad):
        raise ConfiguracionInvalida("Identidad S3 inválida; se exige SHA-256 hexadecimal")
    return DESTINOS[ficha["estado"]] + "/" + identidad + "/"


class S3Inbox:
    """Cliente inyectable para ensayos sin AWS, boto3 ni red."""

    def __init__(self, args, *, cliente=None, fabrica_publicador=None, fabrica_embeddings=None):
        self.args = args
        if args.command != "intake":
            raise ConfiguracionInvalida("El buzón S3 solo admite el comando intake")
        self.bucket, self.prefijo = analizar_uri(args.inbox)
        self.state = guard_output(args.state or Path(".offline") / args.collection)
        self.opciones = {"entrada_temporal": True}
        if fabrica_publicador is not None:
            self.opciones["fabrica_publicador"] = fabrica_publicador
        if fabrica_embeddings is not None:
            self.opciones["fabrica_embeddings"] = fabrica_embeddings
        # Validar destinos locales antes de crear cliente o efectuar solicitudes.
        self._intake(self.state, "0" * 64).validar_estado()
        self.cliente = cliente
        self.ultimo_intake = None

    def _intake(self, estado, identidad):
        args = copy.copy(self.args)
        args.state = estado
        args.inbox = estado / "s3_inbox" / identidad
        return Intake(args, **self.opciones)

    def _listar(self):
        token = None
        while True:
            opciones = {"Bucket": self.bucket, "Prefix": self.prefijo}
            if token:
                opciones["ContinuationToken"] = token
            pagina = self.cliente.list_objects_v2(**opciones)
            yield from pagina.get("Contents", [])
            if not pagina.get("IsTruncated"):
                break
            siguiente = pagina.get("NextContinuationToken")
            if not siguiente or siguiente == token:
                raise RuntimeError("Paginación S3 sin avance")
            token = siguiente

    def _head(self, clave):
        try:
            return self.cliente.head_object(Bucket=self.bucket, Key=clave)
        except Exception as exc:
            if codigo_error(exc) in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def _evento(self, intake, estado, identidad=None, **datos):
        if self.args.dry_run:
            return
        intake._evento(
            {
                "estado": estado,
                "coleccion": self.args.collection,
                "s3": {
                    "bucket": self.bucket,
                    "prefijo": self.prefijo,
                    "clave_sha256": identidad,
                    **datos,
                },
            }
        )

    def registrar_error(self, exc):
        codigo = codigo_error(exc)
        intake = self.ultimo_intake or self._intake(self.state, "0" * 64)
        self._evento(intake, "error_s3", codigo=codigo)
        print(
            f"Error S3: {codigo}; el original permanece en el buzón si no se movió", file=sys.stderr
        )

    def _descargar(self, clave, cabecera, ruta, maximo):
        temporal = ruta.with_suffix(".part")
        temporal.unlink(missing_ok=True)
        try:
            opciones = {"Bucket": self.bucket, "Key": clave, "IfMatch": cabecera["ETag"]}
            if "VersionId" in cabecera:
                opciones["VersionId"] = cabecera["VersionId"]
            respuesta = self.cliente.get_object(**opciones)
            with closing(respuesta["Body"]) as entrada, temporal.open("xb") as salida:
                leidos = 0
                while bloque := entrada.read(min(1024 * 1024, maximo + 1 - leidos)):
                    leidos += len(bloque)
                    if leidos > maximo:
                        raise RuntimeError("El objeto S3 creció por encima del límite de descarga")
                    salida.write(bloque)
            if leidos != cabecera["ContentLength"]:
                raise RuntimeError("Tamaño S3 distinto al de la descarga")
            temporal.replace(ruta)
        finally:
            temporal.unlink(missing_ok=True)

    def _destino_valido(self, destino, cabecera, identidad, recibo):
        copia = self._head(destino + "original.pdf")
        if not copia:
            return None
        if (
            copia["ContentLength"] != cabecera["ContentLength"]
            or copia.get("Metadata", {}).get("identidad-intake") != identidad
        ):
            raise RuntimeError("Destino S3 existente incompatible; se conserva el buzón")
        contenido = recibo.get("ficha", {}).get("hash")
        if contenido and copia.get("Metadata", {}).get("sha256") != contenido:
            raise RuntimeError("SHA-256 del destino S3 incompatible")
        if recibo.get("etag_destino") and copia["ETag"] != recibo["etag_destino"]:
            raise RuntimeError("El destino S3 cambió desde su verificación")
        # El original se copia únicamente después de confirmar los dos informes.
        for nombre in ("ficha.json", "motivo.txt"):
            if not self._head(destino + nombre):
                raise RuntimeError("Destino S3 incompleto; se conserva el buzón")
        return copia

    def _copiar(self, clave, destino, cabecera, identidad, ficha):
        salida = {
            "Bucket": self.bucket,
            "Key": destino + "original.pdf",
            "Metadata": {
                "identidad-intake": identidad,
                "sha256": ficha.get("hash") or "no-calculado",
            },
            "ContentType": "application/pdf",
        }
        origen = {
            "CopySource": {"Bucket": self.bucket, "Key": clave},
            "CopySourceIfMatch": cabecera["ETag"],
        }
        if "VersionId" in cabecera:
            origen["CopySource"]["VersionId"] = cabecera["VersionId"]
        tamano = cabecera["ContentLength"]
        if tamano <= 5_000_000_000:
            return self.cliente.copy_object(**salida, **origen, MetadataDirective="REPLACE")[
                "CopyObjectResult"
            ]["ETag"]
        # CopyObject tiene un límite de 5 GB. También los rechazos mayores se
        # trasladan enteramente dentro de S3, mediante copia por partes.
        carga = self.cliente.create_multipart_upload(**salida)
        destino_carga = {"Bucket": self.bucket, "Key": salida["Key"], "UploadId": carga["UploadId"]}
        partes = []
        paso = max(128 * 1024 * 1024, (tamano + 9999) // 10000)
        try:
            for numero, inicio in enumerate(range(0, tamano, paso), 1):
                parte = self.cliente.upload_part_copy(
                    **destino_carga,
                    **origen,
                    PartNumber=numero,
                    CopySourceRange=f"bytes={inicio}-{min(inicio + paso, tamano) - 1}",
                )
                partes.append({"PartNumber": numero, "ETag": parte["CopyPartResult"]["ETag"]})
            return self.cliente.complete_multipart_upload(
                **destino_carga, MultipartUpload={"Parts": partes}
            )["ETag"]
        except BaseException:
            try:
                self.cliente.abort_multipart_upload(**destino_carga)
            except Exception as exc:
                self._evento(self.ultimo_intake, "s3_limpieza_pendiente", codigo=codigo_error(exc))
            raise

    def _mover(self, intake, clave, cabecera, ficha, identidad, recibo, registro):
        destino = destino_ficha(ficha, identidad)
        copia = self._destino_valido(destino, cabecera, identidad, recibo)
        if copia is None:
            motivos = (
                "\n".join(
                    ["Estado: " + ficha["estado"], *ficha["motivos"], *ficha.get("avisos", [])]
                )
                + "\n"
            )
            for nombre, cuerpo, tipo in (
                ("ficha.json", canonical(ficha), "application/json"),
                ("motivo.txt", motivos.encode("utf-8"), "text/plain; charset=utf-8"),
            ):
                self.cliente.put_object(
                    Bucket=self.bucket, Key=destino + nombre, Body=cuerpo, ContentType=tipo
                )
            etag = self._copiar(clave, destino, cabecera, identidad, ficha)
            copia = self._destino_valido(destino, cabecera, identidad, recibo)
            if not copia or copia["ETag"] != etag:
                raise RuntimeError("No se pudo verificar ETag/tamaño de la copia S3")
            self._evento(intake, "s3_copiado", intake.inbox.name, destino=destino)
        recibo["etag_destino"] = copia["ETag"]
        atomic_bytes(registro, canonical(recibo))
        # No asumir que el productor dejó el objeto intacto durante la publicación.
        if "VersionId" in cabecera:
            self.cliente.delete_object(
                Bucket=self.bucket, Key=clave, VersionId=cabecera["VersionId"]
            )
        else:
            actual = self._head(clave)
            if actual and any(actual[k] != cabecera[k] for k in ("ETag", "ContentLength")):
                self._evento(
                    intake,
                    "s3_original_conservado",
                    intake.inbox.name,
                    motivo="El original S3 cambió antes del borrado",
                )
                raise RuntimeError("El original S3 cambió; se conserva para otra corrida")
            if actual:
                self.cliente.delete_object(Bucket=self.bucket, Key=clave)
        self._evento(
            intake,
            "s3_movido",
            intake.inbox.name,
            destino=destino,
            resultado=ficha.get("resultado"),
        )
        registro.unlink(missing_ok=True)

    def _objeto(self, estado, objeto):
        clave = objeto["Key"]
        identidad_clave = hashlib.sha256(clave.encode("utf-8")).hexdigest()
        intake = self._intake(estado, identidad_clave)
        self.ultimo_intake = intake
        if not clave.startswith(self.prefijo) or not clave_segura(clave):
            self._evento(
                intake, "s3_ignorado", identidad_clave, motivo="Clave hostil o fuera del prefijo"
            )
            return 0
        if clave.endswith("/"):
            return 0
        cabecera = self._head(clave)
        if cabecera is None:
            return 0
        registro = estado / "s3_transferencias" / (identidad_clave + ".json")
        if not self.args.dry_run and registro.exists():
            recibo = json.loads(registro.read_text(encoding="utf-8"))
            if recibo["origen"] == huella_origen(cabecera):
                ficha = recibo["ficha"]
                if (
                    ficha.get("coleccion") != self.args.collection
                    or ficha.get("config_hash") != intake.hash
                ):
                    raise ConfiguracionInvalida("Transferencia pendiente de otra colección/versión")
                destino = destino_ficha(ficha, recibo["identidad"])
                if self._destino_valido(destino, cabecera, recibo["identidad"], recibo):
                    ficha["resultado"] = "sin cambios"
                    with writer_lock(intake.state, intake.capas, intake.cache):
                        comprobar_worker(intake.state)
                        intake.preparar_estado()
                        intake._informes([ficha])
                        self._mover(
                            intake, clave, cabecera, ficha, recibo["identidad"], recibo, registro
                        )
                    return 0
        maximo = intake.destinos["tamano_maximo_bytes"]

        def finalizar(ficha):
            ficha["nombre_original"] = clave.rsplit("/", 1)[-1]
            ficha["origen_s3"] = f"s3://{self.bucket}/{clave}"
            if self.args.dry_run:
                return
            intake._guardar(ficha)
            if ficha["estado"] not in DESTINOS:
                self._evento(intake, "s3_pendiente", identidad_clave, motivo=ficha["estado"])
                return
            identidad = ficha.get("hash") or ficha["doc_id"].removeprefix(
                "desmesurado-"
            ).removeprefix("error-entrada-")
            recibo = {"origen": huella_origen(cabecera), "ficha": ficha, "identidad": identidad}
            atomic_bytes(registro, canonical(recibo))
            self._mover(intake, clave, cabecera, ficha, identidad, recibo, registro)

        def rechazar(identidad, prefijo, motivo):
            ficha = {
                "doc_id": prefijo + identidad,
                "hash": None,
                "coleccion": self.args.collection,
                "config_hash": intake.hash,
                "configuracion": intake.config,
                "estado": "rechazado",
                "decision": "rechazado",
                "motivos": [motivo],
                "avisos": [
                    "Identidad de metadatos; SHA-256 del contenido no calculado sin descargar"
                ],
                "tiempos": {"total": 0.0},
                "rutas": {},
            }
            if self.args.dry_run:
                finalizar(ficha)
            else:
                with writer_lock(intake.state, intake.capas, intake.cache):
                    comprobar_worker(intake.state)
                    intake.preparar_estado()
                    finalizar(ficha)
                    intake._evento(ficha)
                    intake._informes([ficha])
            print(json.dumps(ficha, ensure_ascii=False))
            return 0

        if cabecera["ContentLength"] > maximo:
            identidad = hashlib.sha256(
                canonical([self.bucket, clave, huella_origen(cabecera)])
            ).hexdigest()
            return rechazar(
                identidad,
                "desmesurado-",
                f"Objeto desmesurado: {cabecera['ContentLength']} bytes supera el tamaño máximo",
            )
        # El nombre del objeto S3 (saneado) da el title de los chunks.
        try:
            intake.inbox.mkdir(parents=True, exist_ok=True)
            ruta = intake.inbox / nombre_visible(clave, "entrada" + "0" * 58)
        except Exception as exc:
            return rechazar(
                identidad_clave,
                "error-entrada-",
                "Error al preparar la descarga: " + codigo_error(exc),
            )
        try:
            self._descargar(clave, cabecera, ruta, maximo)
        except Exception as exc:
            if transitorio(exc) or codigo_error(exc) in AUTORIZACION:
                raise
            return rechazar(
                identidad_clave,
                "error-entrada-",
                "Error permanente de descarga: " + codigo_error(exc),
            )
        try:
            return intake.run(al_resultado=finalizar)
        finally:
            ruta.unlink(missing_ok=True)

    def run(self):
        comprobar_worker(self.state)
        self._intake(self.state, "0" * 64).validar_estado()
        if self.cliente is None:
            self.cliente = cliente_predeterminado()
        if self.args.dry_run:
            with tempfile.TemporaryDirectory(prefix="s3-intake-seco-") as temporal:
                estado = Path(temporal) / "estado"
                if self.state.exists():
                    shutil.copytree(self.state, estado, ignore=shutil.ignore_patterns("s3_inbox"))
                return self._corrida(estado)
        with writer_lock(self.state / "s3_inbox"):
            return self._corrida(self.state)

    def _corrida(self, estado):
        codigo = 0
        # Fijar el listado antes de borrar para no invalidar la paginación.
        for objeto in list(self._listar()):
            codigo = max(codigo, self._objeto(estado, objeto))
        return codigo


def ejecutar(args, *, cliente=None, espera=time.sleep, **opciones):
    codigo, fallos = 0, 0
    buzon = S3Inbox(args, cliente=cliente, **opciones)
    while True:
        try:
            codigo = max(codigo, buzon.run())
            fallos = 0
        except ConfiguracionInvalida:
            raise
        except Exception as exc:
            buzon.registrar_error(exc)
            if codigo_error(exc) in AUTORIZACION or not args.watch or not transitorio(exc):
                return 2
            fallos += 1
        if not args.watch:
            return codigo
        espera(min(60, args.intervalo * 2 ** min(fallos, 6)) if fallos else args.intervalo)
