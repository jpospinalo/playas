"""Prepara S/A/A2/V sin servicios y sin acceder a C1/C2.

Ejecutar con -B. Las únicas salidas son descendientes de fidelidad.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "ingesta"))

from benchmarks.fidelidad.anclas import anclas  # noqa: E402
from ingest.offline.extract import read_document  # noqa: E402


def texto(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8", newline="")


def guardar(ruta, contenido):
    texto(ruta, json.dumps(contenido, ensure_ascii=False, indent=2) + "\n")


def palabras_tsv(tsv):
    """Tesseract entrega comillas literales, sin escapado CSV."""
    palabras = []
    for w in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if w["text"].strip():
            x, y, ancho, alto = [int(w[k]) / 2 for k in ("left", "top", "width", "height")]
            palabras.append(
                {"texto": w["text"], "bbox": [x, y, x + ancho, y + alto], "origen": "TSV Tesseract"}
            )
    return palabras


def main():
    import fitz
    import pdfplumber

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layers-root", type=Path, default=BASE / "trabajo" / "capas_fidelidad")
    parser.add_argument(
        "--pdftotext", type=Path, default=Path("C:/Program Files/Git/mingw64/bin/pdftotext.exe")
    )
    args = parser.parse_args()
    capas = args.layers_root.resolve()
    if not capas.is_relative_to((BASE / "trabajo").resolve()):
        parser.error("--layers-root debe estar dentro de trabajo/")
    seleccion = json.loads((BASE / "seleccion.json").read_text(encoding="utf-8"))
    mapa = json.loads((BASE / "trabajo" / "mapa_originales.json").read_text(encoding="utf-8"))
    fallo = BASE / "trabajo" / "instalacion" / "intento.txt"
    # PowerShell puede escribir el registro con UTF-16LE.
    registro = fallo.read_bytes() if fallo.exists() else b""
    error = registro.decode(
        "utf-16" if registro.startswith(b"\xff\xfe") else "utf-8-sig", errors="replace"
    )
    ocr_listo = False
    if shutil.which("tesseract"):
        idiomas = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, check=False
        )
        ocr_listo = idiomas.returncode == 0 and "spa" in idiomas.stdout.splitlines()
    if not ocr_listo and not error:
        error = "Tesseract no instalado o idioma spa ausente"
    estados = {k: [] for k in ("S", "A", "A2", "V")}
    arbol = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "HEAD", "data/documents/bronze"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    blobs = {}
    for entrada in arbol.split(b"\0"):
        if entrada:
            meta, ruta = entrada.split(b"\t", 1)
            ruta_real = ruta.decode("utf-8")
            blobs[unicodedata.normalize("NFC", ruta_real)] = (
                meta.split()[2].decode("ascii"),
                ruta_real,
            )
    for doc in seleccion["documentos"]:
        identificador = doc["id"]
        original = BASE / "trabajo" / "originales" / doc["archivo"]
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        if mapa[doc["archivo"]]["sha256"] != digest or mapa[doc["archivo"]]["ruta"] != doc["ruta"]:
            raise ValueError("Original o mapa no corresponde a la selección: " + identificador)
        digital = doc["tipo_pagina"] == "digital"
        documento = None
        if digital or ocr_listo:
            # Misma función que LayerStore.process; sin importar pipeline/chunks/embeddings.
            documento = read_document(original, capas / "cache")
            excluidos = {
                "raw_pages",
                "original",
                "new_ocr_pages",
                "cpu_seconds",
                "ocr_seconds",
                "extraction_cache_hit",
            }
            extraccion = {k: v for k, v in documento.items() if k not in excluidos}
            extraccion.update(
                {
                    "original_file": Path(documento["original_file"]).name,
                    "chars_per_page": [len(re.sub(r"\s", "", p)) for p in documento["raw_pages"]],
                    "errors": [
                        {"page": p, "reason": "ocr_failed"} for p in documento["ocr_failed_pages"]
                    ],
                }
            )
            texto(capas / "bronze" / (digest + ".txt"), documento["original"])
            guardar(capas / "bronze" / (digest + ".extraction.json"), extraccion)
            partes = documento["original"].split("\n\f\n")
            for pagina in doc["paginas"]:
                if pagina in documento["ocr_failed_pages"]:
                    estados["S"].append(
                        {
                            "documento": identificador,
                            "pagina": pagina,
                            "estado": "PENDIENTE",
                            "error": error or "ocr_failed",
                        }
                    )
                    continue
                texto(
                    BASE / "fuentes" / "S" / identificador / f"{pagina:03d}.txt", partes[pagina - 1]
                )
                estados["S"].append(
                    {
                        "documento": identificador,
                        "pagina": pagina,
                        "estado": "disponible",
                        "origen": "OCR" if pagina in documento["ocr_pages"] else "texto PDF",
                        "confianza_ocr": documento["ocr_confidence"].get(str(pagina)),
                        "doc_id": digest,
                    }
                )
        else:
            for pagina in doc["paginas"]:
                estados["S"].append(
                    {
                        "documento": identificador,
                        "pagina": pagina,
                        "estado": "PENDIENTE",
                        "origen": "OCR",
                        "confianza_ocr": None,
                        "error": error,
                    }
                )
        ruta_v = "data/documents/bronze/" + str(Path(doc["ruta"]).with_suffix(".md")).replace(
            "\\", "/"
        )
        sha, ruta_v = blobs.get(ruta_v, (None, ruta_v))
        markdown = (
            unicodedata.normalize(
                "NFC",
                subprocess.run(
                    ["git", "cat-file", "blob", sha], cwd=REPO, capture_output=True, check=True
                ).stdout.decode("utf-8-sig"),
            )
            if sha
            else None
        )
        if markdown is not None:
            # Registra el blob para verificar la procedencia sin tocar sparse checkout.
            guardar(
                BASE / "fuentes" / "V" / identificador / "procedencia.json",
                {"ruta_git": ruta_v, "blob": sha},
            )
        tramos = []
        with pdfplumber.open(original) as plumber, fitz.open(original) as pdf:
            for pagina in doc["paginas"]:
                contexto = {
                    "documento": identificador,
                    "pagina": pagina,
                    "tipo_pagina": doc["tipo_pagina"],
                }
                resultado = subprocess.run(
                    [
                        str(args.pdftotext),
                        "-enc",
                        "UTF-8",
                        "-f",
                        str(pagina),
                        "-l",
                        str(pagina),
                        str(original),
                        "-",
                    ],
                    capture_output=True,
                    check=True,
                )
                a = resultado.stdout.decode("utf-8")
                texto(BASE / "fuentes" / "A" / identificador / f"{pagina:03d}.txt", a)
                estados["A"].append(
                    {
                        **contexto,
                        "estado": "disponible" if a.strip() else "no aplica",
                        "motivo": None if a.strip() else "sin capa de texto",
                        "comando": "pdftotext -enc UTF-8 -f N -l N original - (sin -layout)",
                    }
                )
                a2 = plumber.pages[pagina - 1].extract_text() or ""
                texto(BASE / "fuentes" / "A2" / identificador / f"{pagina:03d}.txt", a2)
                estados["A2"].append(
                    {**contexto, "estado": "disponible" if a2.strip() else "no aplica"}
                )
                palabras = [
                    {"texto": w[4], "bbox": list(w[:4]), "origen": "PyMuPDF"}
                    for w in pdf[pagina - 1].get_text("words", sort=True)
                ]
                if not digital and ocr_listo:
                    # El pipeline consume TSV pero no lo conserva: se repite SU comando
                    # con idéntica imagen 2x, spa, psm=3 y OMP_THREAD_LIMIT=1.
                    imagen = (
                        pdf[pagina - 1]
                        .get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                        .tobytes("png")
                    )
                    tsv = subprocess.run(
                        ["tesseract", "stdin", "stdout", "-l", "spa", "--psm", "3", "tsv"],
                        input=imagen,
                        capture_output=True,
                        check=True,
                        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                    ).stdout.decode("utf-8")
                    texto(
                        BASE / "trabajo" / "coordenadas" / identificador / f"{pagina:03d}.tsv", tsv
                    )
                    palabras = palabras_tsv(tsv)
                guardar(
                    BASE / "trabajo" / "coordenadas" / identificador / f"{pagina:03d}.json",
                    palabras,
                )
                if markdown is None:
                    estados["V"].append(
                        {
                            **contexto,
                            "estado": "fuente ausente",
                            "motivo": "blob no encontrado",
                            "ruta_git": ruta_v,
                        }
                    )
                    continue
                candidatos = []
                for fuente_ancla, ancla in (
                    ("S", documento["raw_pages"][pagina - 1] if documento else ""),
                    ("A", a),
                ):
                    rango, metodo = anclas(ancla, markdown)
                    candidatos.append((rango, {**metodo, "fuente_ancla": fuente_ancla}))
                viables = [c for c in candidatos if c[0]]
                rango, metodo = (
                    min(
                        viables,
                        key=lambda c: c[1]["palabras_antes_ancla"] + c[1]["palabras_despues_ancla"],
                    )
                    if viables
                    else candidatos[-1]
                )
                tramos.append((pagina, rango, metodo))
        anterior = -1
        for pagina, rango, metodo in tramos:
            if rango and rango[0] >= anterior:
                inicio, fin = rango
                texto(
                    BASE / "fuentes" / "V" / identificador / f"{pagina:03d}.txt",
                    markdown[inicio:fin],
                )
                estados["V"].append(
                    {"documento": identificador, "pagina": pagina, "estado": "alineado", **metodo}
                )
                anterior = fin
            else:
                texto(BASE / "fuentes" / "V" / identificador / "documento.txt", markdown)
                if rango:
                    metodo["motivo"] = (
                        "tramo se superpone con página anterior seleccionada; no se atribuye por página"
                    )
                estados["V"].append(
                    {
                        "documento": identificador,
                        "pagina": pagina,
                        "estado": "solo_documento",
                        **metodo,
                    }
                )
    for fuente, paginas in estados.items():
        guardar(
            BASE / "fuentes" / fuente / "paginas.json",
            {
                "paginas": paginas,
                **(
                    {
                        "tesseract": "instalado" if ocr_listo else "PENDIENTE",
                        "error_instalacion": error,
                        "registro": "trabajo/instalacion/intento.txt",
                    }
                    if fuente == "S"
                    else {}
                ),
            },
        )
    guardar(
        BASE / "trabajo" / "preparacion.json",
        {
            "capas": str(capas),
            "tesseract": ocr_listo,
            "conteos": {
                k: dict(__import__("collections").Counter(p["estado"] for p in v))
                for k, v in estados.items()
            },
        },
    )
    print(
        json.dumps(
            {
                k: dict(__import__("collections").Counter(p["estado"] for p in v))
                for k, v in estados.items()
            }
        )
    )


if __name__ == "__main__":
    main()
