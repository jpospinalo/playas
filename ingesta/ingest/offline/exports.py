"""Paquetes JSONL comprimidos con manifiesto verificable, sin conexiones al verificar."""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ..offline_embeddings import validate_vector
from .extract import sha256_file
from .layers import canonical, signature
from .storage import atomic_bytes, atomic_stream, guard_output, input_scope, writer_lock


def escribir_exportacion(path, config, config_hash, coleccion, registros):
    path = guard_output(path)
    digest = hashlib.sha256()
    cantidad = 0
    documentos = set()
    with (
        atomic_stream(path) as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as comprimido,
        io.TextIOWrapper(comprimido, encoding="utf-8", newline="\n") as salida,
    ):
        salida.write(
            json.dumps(
                {"__manifest__": {**config, "config_hash": config_hash, "collection": coleccion}}
            )
            + "\n"
        )
        for registro in registros:
            validate_vector(registro["embedding"])
            linea = json.dumps(registro, ensure_ascii=False, allow_nan=False) + "\n"
            salida.write(linea)
            digest.update(linea.encode())
            cantidad += 1
            documentos.add(registro["metadata"]["doc_id"])
    manifiesto = {
        "configuration": config,
        "config_hash": config_hash,
        "coleccion": coleccion,
        "records": cantidad,
        "documentos": len(documentos),
        "records_sha256": digest.hexdigest(),
        "compressed_sha256": sha256_file(path),
        "archivos": {path.name: sha256_file(path)},
    }
    lateral = path.with_name(path.name + ".manifest.json")
    # Mantener exportación determinista: la fecha es la de la primera instantánea
    # idéntica; cambia cuando cambia algún byte o la configuración.
    anterior = json.loads(lateral.read_text(encoding="utf-8")) if lateral.exists() else {}
    fecha = (
        anterior.get("fecha")
        if {k: v for k, v in anterior.items() if k != "fecha"} == manifiesto
        else None
    )
    manifiesto["fecha"] = fecha or dt.datetime.now(dt.UTC).isoformat()
    atomic_bytes(lateral, canonical(manifiesto))
    return cantidad


def verificar_exportacion(path):
    from .pipeline import config_hash

    path = Path(path)
    manifiesto = json.loads(
        path.with_name(path.name + ".manifest.json").read_text(encoding="utf-8")
    )
    if manifiesto["config_hash"] not in {
        signature(manifiesto["configuration"]),
        config_hash(manifiesto["configuration"]),
    }:
        raise ValueError("config_hash no corresponde a la configuración exportada")
    digest_archivo = sha256_file(path)
    if (
        manifiesto["archivos"] != {path.name: digest_archivo}
        or manifiesto["compressed_sha256"] != digest_archivo
    ):
        raise ValueError("SHA-256 del archivo exportado no coincide")
    digest = hashlib.sha256()
    ids, documentos = set(), set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as entrada:
        cabecera = json.loads(next(entrada))["__manifest__"]
        if (
            cabecera["config_hash"] != manifiesto["config_hash"]
            or cabecera["collection"] != manifiesto["coleccion"]
        ):
            raise ValueError("Configuración o colección no coincide")
        if {k: cabecera[k] for k in manifiesto["configuration"]} != manifiesto["configuration"]:
            raise ValueError("Configuración del manifiesto inconsistente")
        for linea in entrada:
            registro = json.loads(linea)
            validate_vector(registro["embedding"])
            if registro["id"] in ids:
                raise ValueError("Ids duplicados en la exportación")
            ids.add(registro["id"])
            documentos.add(registro["metadata"]["doc_id"])
            digest.update(linea.encode())
    if (
        len(ids) != manifiesto["records"]
        or len(documentos) != manifiesto["documentos"]
        or digest.hexdigest() != manifiesto["records_sha256"]
    ):
        raise ValueError("Conteos o SHA-256 de registros no coinciden")
    dt.datetime.fromisoformat(manifiesto["fecha"])
    return {
        "verificado": True,
        "registros": len(ids),
        "documentos": len(documentos),
        "config_hash": manifiesto["config_hash"],
        "coleccion": manifiesto["coleccion"],
    }


def exportar_intake(args):
    """Exporta solo fichas publicadas usando vectores ya confirmados en la caché."""
    estado = args.state or Path(".offline") / args.collection
    with input_scope(args.input_dir), writer_lock(estado, args.layers_root, args.cache):
        ajustes = json.loads((estado / "intake_config.json").read_text(encoding="utf-8"))
        if ajustes["coleccion"] != args.collection:
            raise ValueError("El estado pertenece a otra colección")
        fichas = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((estado / "intake").glob("*.json"))
        ]
        publicadas = [f for f in fichas if f["estado"] == "publicado"]
        if not publicadas:
            raise ValueError("No hay documentos publicados para exportar")
        config = publicadas[0]["configuracion"]
        ficticios = config["model"] == "bench_hash"
        cache = guard_output(
            args.cache / ("bench_embeddings.sqlite" if ficticios else "embeddings.sqlite")
        )
        with closing(sqlite3.connect(cache.as_uri() + "?mode=ro", uri=True)) as db:

            def registros():
                for ficha in publicadas:
                    if ficha["config_hash"] != ajustes["config_hash"]:
                        raise ValueError("Ficha de otra configuración")
                    for chunk in ficha["chunks"]:
                        clave = hashlib.sha256(
                            (config["digest"] + "\0" + chunk["document"]).encode()
                        ).hexdigest()
                        fila = db.execute(
                            "SELECT vector FROM vectors WHERE key=?", (clave,)
                        ).fetchone()
                        if fila is None:
                            raise ValueError("Falta un embedding en la caché; reintentar intake")
                        yield {
                            "id": chunk["id"],
                            "document": chunk["document"],
                            "metadata": chunk["metadata"],
                            "embedding": json.loads(fila[0]),
                        }

            return escribir_exportacion(
                args.file, config, ajustes["config_hash"], args.collection, registros()
            )
