"""Vuelve el worker a la línea base del demo (se ejecuta EN el worker, servicio parado).

- Retira de la colección y __staging todo documento que no esté en la base
  (/var/lib/atlas/base_hashes.txt, escrito por construir_base.sh).
- Borra sus fichas e instantáneas para que volver a subirlos se procese como nuevo.
- Archiva sus objetos S3 de processed/, review/ y rejected/ en archive/<fecha>/.
- Con --frio vacía también las cachés (OCR, extracción, embeddings): el siguiente
  procesamiento es en frío. Sin --frio, re-subir el mismo PDF reutiliza la caché.
Sin claves: S3 con el perfil de instancia.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

from ingest.offline.intake_safety import (
    ConfiguracionInvalida,
    cargar_destinos,
    validar_destino,
)

DATOS = Path("/var/lib/atlas")
ESTADO = DATOS / "estado"


def reconciliar_documentos(cliente, coleccion, estado, documentos):
    """Retira restos de cualquier estado antes de borrar la evidencia local."""
    from chromadb.errors import NotFoundError

    validar_destino(coleccion, "127.0.0.1", cargar_destinos())
    registro = estado / "intake_config.json"
    if (
        not registro.exists()
        or json.loads(registro.read_text(encoding="utf-8")).get("coleccion") != coleccion
    ):
        raise ConfiguracionInvalida("La colección no coincide con la registrada en el estado local")

    colecciones = []
    for nombre in (coleccion, coleccion + "__staging"):
        try:
            colecciones.append(cliente.get_collection(nombre))
        except NotFoundError:
            pass
    retirados = 0
    for doc_id in documentos:
        habia = False
        for destino in colecciones:
            if destino.get(where={"doc_id": doc_id}, include=[])["ids"]:
                habia = True
                destino.delete(where={"doc_id": doc_id})
        for destino in colecciones:
            if destino.get(where={"doc_id": doc_id}, include=[])["ids"]:
                raise RuntimeError(
                    f"Quedan chunks de {doc_id} en {destino.name}; se conserva la ficha"
                )
        (estado / "intake" / f"{doc_id}.json").unlink(missing_ok=True)
        (estado / "intake" / "instantaneas" / f"{doc_id}.jsonl.gz").unlink(missing_ok=True)
        retirados += habia
    return retirados


def archivar_objeto(s3, bucket, clave, destino):
    """Copia gestionada (incluye multiparte) fijando la versión de origen."""
    cabecera = s3.head_object(Bucket=bucket, Key=clave)
    origen = {"Bucket": bucket, "Key": clave}
    borrado = {"Bucket": bucket, "Key": clave}
    if "VersionId" in cabecera:
        origen["VersionId"] = borrado["VersionId"] = cabecera["VersionId"]
    s3.copy(origen, bucket, destino, ExtraArgs={"CopySourceIfMatch": cabecera["ETag"]})
    if "VersionId" not in cabecera:
        actual = s3.head_object(Bucket=bucket, Key=clave)
        if any(actual[k] != cabecera[k] for k in ("ETag", "ContentLength")):
            raise RuntimeError(f"El objeto {clave} cambió; se conserva el original")
    s3.delete_object(**borrado)


def main():
    frio = "--frio" in sys.argv[1:]
    bucket, coleccion = os.environ["ATLAS_BUCKET"], os.environ["ATLAS_COLECCION"]
    base = set((DATOS / "base_hashes.txt").read_text(encoding="utf-8").split())
    if not base:
        sys.exit("base_hashes.txt vacío: construir la base antes de reiniciar")
    fichas = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in (ESTADO / "intake").glob("*.json")
    }
    demo = sorted(d for d in fichas if d not in base)
    import chromadb

    cliente = chromadb.HttpClient(host="127.0.0.1", port=8000)
    retirados = reconciliar_documentos(cliente, coleccion, ESTADO, demo)
    cola = ESTADO / "review_queue.csv"
    if cola.exists():
        with cola.open(encoding="utf-8", newline="") as entrada:
            filas = list(csv.DictReader(entrada))
        conservar = [f for f in filas if not any(d in json.dumps(f) for d in demo)]
        if filas:
            with cola.open("w", encoding="utf-8", newline="") as salida:
                w = csv.DictWriter(salida, fieldnames=list(filas[0]))
                w.writeheader()
                w.writerows(conservar)
    import boto3

    s3 = boto3.client("s3")
    marca = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    movidos = 0
    for prefijo in ("processed", "review", "rejected"):
        for pagina in s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefijo + "/"
        ):
            for obj in pagina.get("Contents", []):
                partes = obj["Key"].split("/")
                if len(partes) > 2 and partes[1] not in base:
                    destino = f"archive/{marca}/{obj['Key']}"
                    archivar_objeto(s3, bucket, obj["Key"], destino)
                    movidos += 1
    if frio:
        for hijo in (DATOS / "cache").iterdir():
            shutil.rmtree(hijo) if hijo.is_dir() else hijo.unlink()
        # Las capas bronze/silver/gold también evitan rehacer el OCR: en frío se
        # borran las de los documentos del demo (las de la base se conservan).
        import sqlite3

        # Cualquier doc_id ajeno a la base (aunque un reinicio previo borrara su ficha).
        with sqlite3.connect(ESTADO / "intake_layers.sqlite") as db:
            ajenos = {d for (d,) in db.execute("SELECT DISTINCT doc_id FROM layers")} - base
            for doc_id in ajenos:
                db.execute("DELETE FROM layers WHERE doc_id=?", (doc_id,))
        ajenos |= {p.name.split(".", 1)[0] for p in (DATOS / "capas").glob("*/*.*")} - base
        for doc_id in ajenos:
            for archivo in (DATOS / "capas").glob(f"*/{doc_id}.*"):
                archivo.unlink()
    print(
        f"Línea base restaurada: {len(demo)} documentos de demo limpiados ({retirados} retirados de Chroma), "
        f"{movidos} objetos S3 archivados en archive/{marca}/, cachés {'vaciadas' if frio else 'conservadas'}."
    )


if __name__ == "__main__":
    main()
