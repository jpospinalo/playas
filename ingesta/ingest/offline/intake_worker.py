"""Aislamiento del analizador PDF y las capas: timeout externo y memoria en Linux."""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from .intake_safety import clasificar, simhash_shingles
from .layers import Layers, canonical
from .policy import senales_documento
from .storage import atomic_bytes, input_scope


def analizar(solicitud):
    import fitz

    pdf = Path(solicitud["pdf"])
    limites = solicitud["destinos"]
    inicio_validacion = time.monotonic()
    # No se ejecuta JavaScript ni se accede a anexos del PDF.
    try:
        with fitz.open(pdf) as documento:
            if documento.needs_pass or documento.is_encrypted:
                return {"rechazo": "PDF cifrado"}
            if documento.page_count == 0:
                return {"rechazo": "PDF vacío: 0 páginas"}
            if documento.page_count > limites["paginas_maximas"]:
                return {"rechazo": "PDF desmesurado: supera páginas máximas"}
            if documento.is_repaired:
                return {"rechazo": "PDF corrupto o truncado: requiere reparación"}
            for pagina in documento:
                pagina.get_text("text")
    except Exception:
        return {"rechazo": "PDF corrupto o truncado: error al abrir o iterar páginas"}
    db = sqlite3.connect(solicitud["db"])
    tiempos = {fase: 0.0 for fase in ("bronze", "silver", "gold", "clasificacion", "senales")}
    tiempos["validacion"] = time.monotonic() - inicio_validacion
    reconstruidas = set()

    def medir(nombre, operacion):
        fase = {
            "extraction": "bronze",
            "metadata": "silver",
            "cleaning": "silver",
            "chunking": "gold",
        }[nombre]
        inicio = time.monotonic()
        reconstruidas.add(fase)
        try:
            return operacion()
        finally:
            tiempos[fase] += time.monotonic() - inicio

    categoria = {}

    def tipo(documento):
        inicio = time.monotonic()
        categoria.update(clasificar(documento, solicitud.get("categoria")))
        tiempos["clasificacion"] += time.monotonic() - inicio
        return categoria["categoria"]

    try:
        with input_scope(solicitud["inbox"]):
            capas = Layers(solicitud["capas"], db, solicitud["inbox"])
            doc_id = solicitud["doc_id"]
            capas.restore(doc_id, solicitud.get("desde"))
            documento, metadata, limpio, chunks, cambios = capas.build(
                doc_id,
                [pdf.name],
                pdf.parent,
                Path(solicitud["cache"]),
                solicitud["config"],
                [],
                solicitud["config"]["digest"],
                solicitud.get("desde"),
                medir,
                doc_type=tipo,
            )
            inicio = time.monotonic()
            senales = senales_documento(solicitud["capas"], doc_id, pdf, categoria["categoria"])
            tiempos["senales"] = time.monotonic() - inicio
            db.commit()
            capas.persist()
            return {
                "clasificacion": categoria,
                "senales": senales,
                "chunks": chunks,
                "metricas": {
                    "bronze": capas.read_json("bronze", doc_id, ".quality.json"),
                    "silver": {"caracteres": len(limpio["text"]), "paginas": len(limpio["pages"])},
                    "gold": {"chunks": len(chunks)},
                },
                "tiempos": tiempos,
                "fases": {
                    fase: {
                        "accion": "Reconstruida"
                        if fase in reconstruidas
                        else "Reutilizada y verificada",
                        "estado": "completada",
                        "segundos": tiempos[fase],
                    }
                    for fase in ("bronze", "silver", "gold")
                },
                "capas_reconstruidas": cambios,
                "simhash": simhash_shingles(limpio["text"], limites["simhash_palabras_shingle"]),
            }
    finally:
        db.close()


def main():
    solicitud = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if sys.platform.startswith("linux"):
        import resource

        memoria = solicitud["destinos"]["memoria_maxima_mb"] * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memoria, memoria))
    try:
        resultado = analizar(solicitud)
    except Exception as exc:
        resultado = {"error": f"Error de extracción/capas: {type(exc).__name__}: {exc}"}
    atomic_bytes(solicitud["resultado"], canonical(resultado))


if __name__ == "__main__":
    main()
